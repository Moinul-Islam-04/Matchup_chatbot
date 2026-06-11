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

    ally_tips = champ.get("allytips") or []
    enemy_tips = champ.get("enemytips") or []

    sections = [
        f"# {name} — {title}",
        f"**Class:** {tags}  |  **Resource:** {partype}  |  **Patch:** {version}",
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


def format_live_match(
    game: dict[str, Any],
    champ_name_by_key: dict[int, str],
    queried_puuid: str | None = None,
) -> str:
    """Render a Spectator-V5 active-game payload as an LLM-friendly briefing.

    Args:
        game: raw Spectator-V5 ``active-games`` response.
        champ_name_by_key: numeric championId -> display name (resolved upstream).
        queried_puuid: if provided, the queried player is marked with "(you)".
    """
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
            lines.append(f"- **{champ}**{role} — {riot_id}{you}")

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
