"""Turn raw Data Dragon champion payloads into compact, LLM-friendly markdown.

We deliberately format for a language model consumer, not a human dashboard:
short labeled sections, the numbers that matter for matchup reasoning (base
stats + per-level growth), ability names with cooldowns, and Riot's own
ally/enemy tips which are a decent proxy for "powerspike / matchup context".
"""

from __future__ import annotations

from typing import Any

# (base_key, label, growth_key, growth_is_percent)
# Riot stores attack-speed growth as a raw percent (e.g. 2 -> +2%/lvl).
_STAT_LABELS = [
    ("hp", "HP", "hpperlevel", False),
    ("mp", "Resource", "mpperlevel", False),
    ("armor", "Armor", "armorperlevel", False),
    ("spellblock", "MR", "spellblockperlevel", False),
    ("attackdamage", "AD", "attackdamageperlevel", False),
    ("attackspeed", "Attack Speed", "attackspeedperlevel", True),
    ("movespeed", "Move Speed", None, False),
    ("attackrange", "Range", None, False),
]

_SLOT_KEYS = ["Q", "W", "E", "R"]


def _fmt_num(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _stats_block(stats: dict[str, Any]) -> str:
    lines = []
    for base_key, label, growth_key, growth_pct in _STAT_LABELS:
        if base_key not in stats:
            continue
        base = _fmt_num(stats[base_key])
        if growth_key and stats.get(growth_key):
            suffix = "%" if growth_pct else ""
            lines.append(f"- {label}: {base} (+{_fmt_num(stats[growth_key])}{suffix}/lvl)")
        else:
            lines.append(f"- {label}: {base}")
    return "\n".join(lines)


def _abilities_block(passive: dict[str, Any], spells: list[dict[str, Any]]) -> str:
    lines = []
    p_name = passive.get("name", "Passive")
    p_desc = _strip_tags(passive.get("description", ""))
    lines.append(f"- **Passive — {p_name}:** {p_desc}")
    for slot, spell in zip(_SLOT_KEYS, spells):
        name = spell.get("name", "")
        desc = _strip_tags(spell.get("description", ""))
        cd = spell.get("cooldownBurn", "")
        cost = spell.get("costBurn", "")
        meta = []
        if cd:
            meta.append(f"CD {cd}s")
        if cost and cost not in ("0", "No Cost"):
            meta.append(f"cost {cost}")
        meta_str = f" ({'; '.join(meta)})" if meta else ""
        lines.append(f"- **{slot} — {name}{meta_str}:** {desc}")
    return "\n".join(lines)


# Champions that are MELEE-classed for item/rune interactions despite a long
# basic-attack range (so an attackrange heuristic alone mislabels them). This
# matters for effects like Conqueror that penalize ranged champions.
_KNOWN_MELEE_LONG_RANGE = {"Graves"}


def _attack_type(name: str, attackrange: float) -> str:
    """Melee vs Ranged for rune/item purposes. Range cleanly separates the two
    for almost every champion (~175 melee vs ~500+ ranged); a small exception
    set covers melee-classed champions with deceptively long range."""
    if name in _KNOWN_MELEE_LONG_RANGE:
        return "Melee"
    return "Melee" if attackrange < 350 else "Ranged"


def _strip_tags(text: str) -> str:
    """Data Dragon descriptions embed <br>, <font>, <i> markup; flatten them."""
    import re

    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def format_champion_info(champ: dict[str, Any], version: str) -> str:
    name = champ.get("name", "?")
    title = champ.get("title", "")
    tags = ", ".join(champ.get("tags", []))
    partype = champ.get("partype", "")
    blurb = _strip_tags(champ.get("blurb", ""))
    attack_type = _attack_type(name, champ.get("stats", {}).get("attackrange", 0))

    ally_tips = champ.get("allytips") or []
    enemy_tips = champ.get("enemytips") or []

    sections = [
        f"# {name} — {title}",
        f"**Class:** {tags}  |  **Attack type:** {attack_type}  "
        f"|  **Resource:** {partype}  |  **Patch:** {version}",
        "",
        "## Base Stats (level 1, with per-level growth)",
        _stats_block(champ.get("stats", {})),
        "",
        "## Abilities",
        _abilities_block(champ.get("passive", {}), champ.get("spells", [])),
        "",
        "## Overview",
        blurb,
    ]

    if ally_tips:
        sections += ["", "## Playing AS this champion (powerspike / combo cues)"]
        sections += [f"- {_strip_tags(t)}" for t in ally_tips]
    if enemy_tips:
        sections += ["", "## Playing AGAINST this champion (matchup cues)"]
        sections += [f"- {_strip_tags(t)}" for t in enemy_tips]

    return "\n".join(sections)


_QUEUE_NAMES = {
    400: "Normal Draft",
    420: "Ranked Solo/Duo",
    430: "Normal Blind",
    440: "Ranked Flex",
    450: "ARAM",
    700: "Clash",
    490: "Quickplay",
    900: "ARURF",
}

# Team id -> friendly side label (Riot uses 100/200).
_TEAM_LABELS = {100: "Blue side", 200: "Red side"}

# Smite's summoner-spell id. It's the only reliable role signal in the Spectator
# payload — a Smite-holder is the jungler. No other lane is inferable.
_SMITE_SPELL_ID = 11

# Apex tiers have no division (always "I") — show tier + LP only.
_APEX_TIERS = {"MASTER", "GRANDMASTER", "CHALLENGER"}


def format_rank(entry: dict[str, Any]) -> str:
    """Format a League-V4 entry as e.g. 'Diamond II · 45 LP' or 'Master · 210 LP'."""
    tier = entry.get("tier", "")
    if not tier:
        return ""
    name = tier.capitalize()
    lp = entry.get("leaguePoints", 0)
    if tier in _APEX_TIERS:
        return f"{name} · {lp} LP"
    return f"{name} {entry.get('rank', '')} · {lp} LP"


def format_live_match(
    game: dict[str, Any],
    champ_name_by_key: dict[int, str],
    queried_puuid: str | None = None,
    rank_by_puuid: dict[str, str] | None = None,
) -> str:
    """Render a Spectator-V5 active-game payload as an LLM-friendly briefing.

    Args:
        game: raw Spectator-V5 ``active-games`` response.
        champ_name_by_key: numeric championId -> display name (resolved upstream).
        queried_puuid: if provided, the queried player is marked with "(you)".
        rank_by_puuid: optional puuid -> formatted ranked tier (e.g. "Diamond II").
    """
    rank_by_puuid = rank_by_puuid or {}
    queue_id = game.get("gameQueueConfigId")
    queue = _QUEUE_NAMES.get(queue_id, f"Queue {queue_id}")
    mode = game.get("gameMode", "")
    length_s = int(game.get("gameLength", 0))
    # Spectator reports a ~3 min negative offset during loading; clamp to >=0.
    mins, secs = divmod(max(length_s, 0), 60)

    participants = game.get("participants", [])
    teams: dict[int, list[dict[str, Any]]] = {}
    for p in participants:
        teams.setdefault(p.get("teamId", 0), []).append(p)

    lines = [
        "# Live Match",
        f"**Queue:** {queue} ({mode})  |  **Elapsed:** {mins}m{secs:02d}s  "
        f"|  **Players:** {len(participants)}",
        "",
        "> IMPORTANT: Riot's live-game API does NOT include lane/role assignments. "
        "The teams below are accurate, but the only role you can infer is the "
        "jungler (marked below — they have Smite). Do NOT guess top/mid/bot "
        "pairings or claim a specific lane opponent. To break down the asked-about "
        "player's lane matchup, first confirm which lane they're in. The champion "
        "they are on is the one tagged `<-- asked about` — note many champions "
        "(e.g. Veigar) are played off-meta in lanes other than their usual one.",
    ]

    for team_id in sorted(teams):
        label = _TEAM_LABELS.get(team_id, f"Team {team_id}")
        lines += ["", f"## {label}"]
        for p in teams[team_id]:
            champ = champ_name_by_key.get(p.get("championId"), f"Champion {p.get('championId')}")
            riot_id = p.get("riotId") or p.get("summonerName") or "?"
            spells = (p.get("spell1Id"), p.get("spell2Id"))
            role = "  _(Jungle — has Smite)_" if _SMITE_SPELL_ID in spells else ""
            you = "  `<-- asked about`" if queried_puuid and p.get("puuid") == queried_puuid else ""
            rank = rank_by_puuid.get(p.get("puuid", ""))
            rank_str = f"  ·  {rank}" if rank else ""
            lines.append(f"- **{champ}**{role} — {riot_id}{rank_str}{you}")

    # Bans, if present, are useful matchup context.
    bans = game.get("bannedChampions") or []
    if bans:
        banned = ", ".join(
            champ_name_by_key.get(b.get("championId"), str(b.get("championId")))
            for b in bans
            if b.get("championId", -1) > 0
        )
        if banned:
            lines += ["", "## Bans", banned]

    return "\n".join(lines)


def build_match_data(
    game: dict[str, Any],
    champ_name_by_key: dict[int, str],
    queried_puuid: str | None = None,
    rank_by_puuid: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Structured live-match data for the UI card (parallel to format_live_match).

    The client renders champion icons from its own Data Dragon maps by name, so
    we only need names/flags here — no image URLs.
    """
    rank_by_puuid = rank_by_puuid or {}
    queue_id = game.get("gameQueueConfigId")

    teams_by_id: dict[int, list[dict[str, Any]]] = {}
    for p in game.get("participants", []):
        teams_by_id.setdefault(p.get("teamId", 0), []).append(p)

    teams = []
    for team_id in sorted(teams_by_id):
        players = []
        for p in teams_by_id[team_id]:
            spells = (p.get("spell1Id"), p.get("spell2Id"))
            players.append(
                {
                    "champion": champ_name_by_key.get(
                        p.get("championId"), f"Champion {p.get('championId')}"
                    ),
                    "riotId": p.get("riotId") or p.get("summonerName") or "?",
                    "isJungle": _SMITE_SPELL_ID in spells,
                    "isYou": bool(queried_puuid and p.get("puuid") == queried_puuid),
                    "rank": rank_by_puuid.get(p.get("puuid", "")),
                }
            )
        teams.append({"side": _TEAM_LABELS.get(team_id, f"Team {team_id}"), "players": players})

    bans = [
        champ_name_by_key.get(b.get("championId"), str(b.get("championId")))
        for b in (game.get("bannedChampions") or [])
        if b.get("championId", -1) > 0
    ]

    return {
        "queue": _QUEUE_NAMES.get(queue_id, f"Queue {queue_id}"),
        "gameLengthSec": max(int(game.get("gameLength", 0)), 0),
        "teams": teams,
        "bans": bans,
    }


def format_item_info(item: dict[str, Any], version: str) -> str:
    """Render a Data Dragon item payload (enriched with build-path names)."""
    name = item.get("name", "?")
    gold = item.get("gold", {})
    total = gold.get("total", 0)
    combine = gold.get("base", 0)
    tags = ", ".join(item.get("tags", []))
    plaintext = item.get("plaintext", "")
    # The description carries stats + passives in markup; flatten it.
    desc = _strip_tags(item.get("description", ""))

    lines = [
        f"# {name} — {total}g  (patch {version})",
    ]
    from_names = item.get("_from_names") or []
    into_names = item.get("_into_names") or []
    if from_names:
        lines.append(f"**Builds from:** {', '.join(from_names)}  (+{combine}g combine)")
    if into_names:
        lines.append(f"**Builds into:** {', '.join(into_names)}")
    if tags:
        lines.append(f"**Tags:** {tags}")
    if plaintext:
        lines += ["", f"_{plaintext}_"]
    if desc:
        lines += ["", "## Stats & effects", desc]
    return "\n".join(lines)


def format_rune_info(rune: dict[str, Any]) -> str:
    """Render a single rune (keystone or minor) with its tree and description."""
    name = rune.get("name", "?")
    tree = rune.get("_tree", "")
    kind = "Keystone" if rune.get("_is_keystone") else "Minor rune"
    long_desc = _strip_tags(rune.get("longDesc", ""))
    short_desc = _strip_tags(rune.get("shortDesc", ""))

    lines = [
        f"# {name}",
        f"**{kind}** in the **{tree}** tree",
    ]
    body = long_desc or short_desc
    if body:
        lines += ["", body]
    return "\n".join(lines)
