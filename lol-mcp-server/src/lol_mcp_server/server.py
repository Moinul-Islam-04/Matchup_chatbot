"""LoL MCP Server entrypoint.

Exposes League of Legends data as MCP tools over the stdio transport.
Phase 1 ships `get_champion_info`; `get_live_match_context` (Spectator API)
lands in the next step.

Logging goes to stderr only (see logging_setup) so JSON-RPC frames on stdout
stay clean.
"""

from __future__ import annotations

import asyncio
import os

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult

from .auth import StaticTokenVerifier
from .config import Config
from .data_dragon import DataDragonClient
from .formatting import (
    build_match_data,
    format_champion_info,
    format_item_info,
    format_live_match,
    format_rank,
    format_rune_info,
)
from .logging_setup import configure_logging, get_logger
from .riot_api import RiotApiError, RiotClient

configure_logging()
log = get_logger("server")

config = Config.from_env()

# Optional bearer-token auth for the HTTP transport. Only enforced when
# MCP_AUTH_TOKEN is set — stdio/local runs stay open.
_auth_token = os.getenv("MCP_AUTH_TOKEN")
if _auth_token:
    log.info("bearer-token auth ENABLED")
mcp = FastMCP(
    name="lol-mcp-server",
    auth=StaticTokenVerifier(_auth_token) if _auth_token else None,
)

# Shared clients so the Data Dragon TTL cache and the httpx pools persist
# across tool calls.
ddragon = DataDragonClient(config)
riot = RiotClient(config)


@mcp.tool
async def get_champion_info(champion_name: str) -> str:
    """Get base stats, abilities, and generic powerspike/matchup context for a
    League of Legends champion.

    Use this when the user mentions a champion by name and you need their kit,
    base stats, ability cooldowns, or general playstyle/matchup notes — e.g.
    "When does Diana powerspike?" or "What does Graves build?".

    Args:
        champion_name: Champion name, e.g. "Graves", "Diana", "Cho'Gath",
            "Wukong". Spelling is matched forgivingly (case/punctuation-insensitive).

    Returns:
        A markdown report: base stats with per-level growth, the full ability
        kit with cooldowns/costs, an overview, and Riot's ally/enemy tips which
        approximate powerspike and matchup cues.
    """
    log.info("get_champion_info(%r)", champion_name)
    champ = await ddragon.get_champion_detail(champion_name)
    if champ is None:
        names = await ddragon.list_champion_names()
        # Suggest close-ish names to help the model recover.
        suggestions = [n for n in names if champion_name.strip().lower()[:3] in n.lower()]
        hint = f" Did you mean one of: {', '.join(suggestions[:8])}?" if suggestions else ""
        return f"No champion found matching '{champion_name}'.{hint}"
    version = await ddragon.get_version()
    return format_champion_info(champ, version)


@mcp.tool
async def get_item_info(item_name: str) -> str:
    """Get an item's cost, build path, stats, and passive/active effects.

    Use this when giving build advice so recommendations are grounded in the
    item's real stats and gold cost on the current patch — e.g. "what does
    Serylda's Grudge give and cost?" or to justify a build order.

    Args:
        item_name: Item name, e.g. "Eclipse", "Serylda's Grudge", "Plated
            Steelcaps". Matched case/punctuation-insensitively.

    Returns:
        Markdown: total/combine cost, what it builds from and into, tags, and
        its full stats and effects.
    """
    log.info("get_item_info(%r)", item_name)
    item = await ddragon.get_item_detail(item_name)
    if item is None:
        return f"No item found matching '{item_name}'."
    version = await ddragon.get_version()
    return format_item_info(item, version)


@mcp.tool
async def get_rune_info(rune_name: str) -> str:
    """Get a rune's tree, whether it's a keystone, and its full description.

    Use this to ground rune advice in the rune's actual effect — e.g. "what
    does Conqueror do?" or "is Grasp or Aftershock better here?".

    Args:
        rune_name: Rune name, e.g. "Conqueror", "Electrocute", "Grasp of the
            Undying". Matched case/punctuation-insensitively.

    Returns:
        Markdown: the rune's name, its tree, keystone/minor classification, and
        its full effect text.
    """
    log.info("get_rune_info(%r)", rune_name)
    rune = await ddragon.find_rune(rune_name)
    if rune is None:
        return f"No rune found matching '{rune_name}'."
    return format_rune_info(rune)


@mcp.tool
async def get_live_match_context(summoner_name: str, tag_line: str) -> ToolResult:
    """Get the live match a player is currently in: both teams' champions,
    players, and bans (via the Riot Spectator API).

    Use this when the user references their own or another player's *current*
    game and you need the actual champion matchups — e.g. "I'm in a game right
    now, who am I up against?" or to ground advice in the real enemy comp.

    Requires a valid RIOT_API_KEY. Players are identified by Riot ID, which is
    "gameName#tagLine" (e.g. "Faker#KR1").

    Args:
        summoner_name: the gameName portion of the Riot ID (before the '#').
        tag_line: the tagLine portion (after the '#'), e.g. "NA1", "KR1".

    Returns:
        A markdown briefing of the live game grouped by team side, with each
        player's ranked tier and the jungler flagged, plus bans — or a clear
        message if the player is not currently in a game.
    """
    log.info("get_live_match_context(%r, %r)", summoner_name, tag_line)
    try:
        account = await riot.get_account_by_riot_id(summoner_name, tag_line)
        puuid = account["puuid"]
        game = await riot.get_active_game_by_puuid(puuid)
    except RiotApiError as exc:
        return str(exc)

    # Resolve the numeric championIds the Spectator API returns into names.
    keys = {p.get("championId") for p in game.get("participants", [])}
    keys |= {b.get("championId") for b in game.get("bannedChampions", [])}
    name_by_key = {
        k: await ddragon.get_champion_name_by_key(k)
        for k in keys
        if isinstance(k, int) and k > 0
    }

    # Enrich each player with their ranked tier (League-V4) — concurrent and
    # best-effort, so a slow/failed lookup never breaks the briefing.
    rank_by_puuid: dict[str, str] = {}
    puuids = [p["puuid"] for p in game.get("participants", []) if p.get("puuid")]

    async def _fetch_rank(pid: str) -> None:
        try:
            entries = await riot.get_league_entries_by_puuid(pid)
        except RiotApiError:
            return
        solo = next((e for e in entries if e.get("queueType") == "RANKED_SOLO_5x5"), None)
        entry = solo or next(
            (e for e in entries if e.get("queueType") == "RANKED_FLEX_SR"), None
        )
        if entry:
            label = format_rank(entry)
            if entry is not solo:
                label += " (Flex)"
            rank_by_puuid[pid] = label

    await asyncio.gather(*(_fetch_rank(pid) for pid in puuids))

    # Curated markdown for the model + structured data for the UI's match card.
    text = format_live_match(
        game, name_by_key, queried_puuid=puuid, rank_by_puuid=rank_by_puuid
    )
    match = build_match_data(
        game, name_by_key, queried_puuid=puuid, rank_by_puuid=rank_by_puuid
    )
    return ToolResult(content=text, structured_content={"match": match})


def main() -> None:
    """Console-script entrypoint.

    Transport is chosen by env so the same code runs locally over stdio (for the
    MCP Inspector and the local Next.js client) and as a hosted Streamable HTTP
    server in the cloud:

      MCP_TRANSPORT=stdio   (default) — JSON-RPC over stdin/stdout
      MCP_TRANSPORT=http              — Streamable HTTP server for deployment

    On HTTP, HOST/PORT/MCP_PATH are configurable; PORT also falls back to the
    platform-provided ``$PORT`` (Render/Railway/etc.).
    """
    import os

    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()

    if transport == "stdio":
        log.info("starting lol-mcp-server (stdio)")
        mcp.run()
        return

    if transport in ("http", "streamable-http"):
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8000"))
        path = os.getenv("MCP_PATH", "/mcp/")
        log.info("starting lol-mcp-server (http) on %s:%s%s", host, port, path)
        # Stateless: each request is independent (no session affinity), which is
        # the robust choice behind load balancers / serverless platforms.
        mcp.run(transport="http", host=host, port=port, path=path, stateless_http=True)
        return

    raise SystemExit(f"Unknown MCP_TRANSPORT: {transport!r} (use 'stdio' or 'http')")


if __name__ == "__main__":
    main()
