"""LoL MCP Server entrypoint.

Exposes League of Legends data as MCP tools over the stdio transport.
Phase 1 ships `get_champion_info`; `get_live_match_context` (Spectator API)
lands in the next step.

Logging goes to stderr only (see logging_setup) so JSON-RPC frames on stdout
stay clean.
"""

from __future__ import annotations

from fastmcp import FastMCP

from .config import Config
from .data_dragon import DataDragonClient
from .formatting import format_champion_info, format_live_match
from .logging_setup import configure_logging, get_logger
from .riot_api import RiotApiError, RiotClient

configure_logging()
log = get_logger("server")

config = Config.from_env()
mcp = FastMCP(name="lol-mcp-server")

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
async def get_live_match_context(summoner_name: str, tag_line: str) -> str:
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
        A markdown briefing of the live game grouped by team side, plus bans —
        or a clear message if the player is not currently in a game.
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
    return format_live_match(game, name_by_key, queried_puuid=puuid)


def main() -> None:
    """Console-script entrypoint. Runs the server over stdio."""
    log.info("starting lol-mcp-server (stdio)")
    mcp.run()  # defaults to stdio transport


if __name__ == "__main__":
    main()
