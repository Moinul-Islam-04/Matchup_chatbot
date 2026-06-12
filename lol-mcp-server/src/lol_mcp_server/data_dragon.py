"""Data Dragon client with an in-process TTL cache.

Data Dragon is Riot's public static-data CDN (champions, items, runes, images).
It is NOT rate-limited the way the live Riot API is, but it serves large JSON
blobs, so we cache aggressively:

  * the versions manifest and the full champion index are fetched once and reused
  * per-champion detail payloads are cached individually
  * every cached entry carries a monotonic expiry; we re-fetch only past TTL

The cache uses ``time.monotonic`` (immune to wall-clock changes) and stores the
parsed dict so repeated tool calls never re-hit the CDN within the TTL window.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Config
from .logging_setup import get_logger

log = get_logger("data_dragon")

DDRAGON_BASE = "https://ddragon.leagueoflegends.com"
VERSIONS_URL = f"{DDRAGON_BASE}/api/versions.json"

# A few champions whose Data Dragon id differs from their display name. Data
# Dragon ids strip punctuation/spaces and use internal codenames in a handful of
# cases. We still match by the human-readable "name" field first; this map is a
# fast path / fallback for common queries.
_NAME_ALIASES = {
    "wukong": "MonkeyKing",
    "nunu": "Nunu",
    "nunu & willump": "Nunu",
    "renata glasc": "Renata",
}


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class DataDragonClient:
    def __init__(self, config: Config, client: httpx.AsyncClient | None = None):
        self._config = config
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._owns_client = client is None
        self._cache: dict[str, _CacheEntry] = {}
        self._resolved_version: str | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # --- cache plumbing -----------------------------------------------------

    def _get_cached(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            log.debug("cache expired: %s", key)
            self._cache.pop(key, None)
            return None
        log.debug("cache hit: %s", key)
        return entry.value

    def _set_cached(self, key: str, value: Any) -> None:
        self._cache[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + self._config.cache_ttl_seconds,
        )

    async def _get_json(self, url: str, cache_key: str) -> Any:
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        log.info("fetching %s", url)
        resp = await self._client.get(url)
        resp.raise_for_status()
        data = resp.json()
        self._set_cached(cache_key, data)
        return data

    # --- version resolution -------------------------------------------------

    async def get_version(self) -> str:
        """Resolve the Data Dragon version, honoring a pinned config value."""
        if self._config.ddragon_version != "latest":
            return self._config.ddragon_version
        if self._resolved_version is not None:
            return self._resolved_version
        versions: list[str] = await self._get_json(VERSIONS_URL, "versions")
        self._resolved_version = versions[0]
        log.info("resolved latest Data Dragon version: %s", self._resolved_version)
        return self._resolved_version

    # --- champion data ------------------------------------------------------

    async def get_champion_index(self) -> dict[str, Any]:
        """Full champion.json index (summary stats + id mapping for all champs)."""
        version = await self.get_version()
        locale = self._config.ddragon_locale
        url = f"{DDRAGON_BASE}/cdn/{version}/data/{locale}/champion.json"
        return await self._get_json(url, f"champ_index:{version}:{locale}")

    def _resolve_champion_id(self, index: dict[str, Any], champion_name: str) -> str | None:
        """Map a free-text champion name to its Data Dragon id key."""
        query = champion_name.strip().lower()
        if not query:
            return None
        if query in _NAME_ALIASES:
            return _NAME_ALIASES[query]
        data = index.get("data", {})
        # exact id match (e.g. "Aatrox")
        for champ_id, champ in data.items():
            if champ_id.lower() == query:
                return champ_id
        # display-name match (e.g. "Cho'Gath", "Dr. Mundo")
        for champ_id, champ in data.items():
            if champ.get("name", "").lower() == query:
                return champ_id
        # forgiving match: strip punctuation/spaces both sides
        squashed = "".join(c for c in query if c.isalnum())
        for champ_id, champ in data.items():
            name = "".join(c for c in champ.get("name", "").lower() if c.isalnum())
            if name == squashed or champ_id.lower() == squashed:
                return champ_id
        return None

    async def get_champion_detail(self, champion_name: str) -> dict[str, Any] | None:
        """Full per-champion payload: stats, abilities, lore, tips, tags.

        Returns ``None`` if the champion name cannot be resolved.
        """
        index = await self.get_champion_index()
        champ_id = self._resolve_champion_id(index, champion_name)
        if champ_id is None:
            return None
        version = await self.get_version()
        locale = self._config.ddragon_locale
        url = f"{DDRAGON_BASE}/cdn/{version}/data/{locale}/champion/{champ_id}.json"
        detail = await self._get_json(url, f"champ_detail:{version}:{locale}:{champ_id}")
        return detail["data"][champ_id]

    async def list_champion_names(self) -> list[str]:
        index = await self.get_champion_index()
        return sorted(c["name"] for c in index.get("data", {}).values())

    async def get_champion_name_by_key(self, key: int | str) -> str:
        """Map a numeric champion key (as the Spectator/Match APIs return) to a
        display name. Falls back to "Champion {key}" if unknown."""
        index = await self.get_champion_index()
        key_str = str(key)
        for champ in index.get("data", {}).values():
            if champ.get("key") == key_str:
                return champ.get("name", key_str)
        return f"Champion {key_str}"

    # --- item data ----------------------------------------------------------

    async def get_item_index(self) -> dict[str, Any]:
        """Full item.json index (stats, gold, build paths for every item)."""
        version = await self.get_version()
        locale = self._config.ddragon_locale
        url = f"{DDRAGON_BASE}/cdn/{version}/data/{locale}/item.json"
        return await self._get_json(url, f"item_index:{version}:{locale}")

    def _resolve_item_id(self, index: dict[str, Any], item_name: str) -> str | None:
        target = item_name.strip().lower()
        squashed = "".join(c for c in target if c.isalnum())
        if not squashed:
            return None
        data = index.get("data", {})

        # Data Dragon ships per-game-mode variants under the same display name
        # (e.g. an Arena "Eclipse" with no build path alongside the Summoner's
        # Rift one). Collect every name match, then prefer the canonical SR,
        # purchasable item with a real build path.
        candidates: list[tuple[str, dict[str, Any]]] = []
        for item_id, item in data.items():
            name = item.get("name", "").lower()
            if name == target or "".join(c for c in name if c.isalnum()) == squashed:
                candidates.append((item_id, item))
        if not candidates:
            return None

        def rank(pair: tuple[str, dict[str, Any]]) -> tuple[int, int, int, int]:
            item_id, item = pair
            on_sr = 1 if item.get("maps", {}).get("11") else 0
            purchasable = 1 if item.get("gold", {}).get("purchasable") else 0
            has_path = 1 if (item.get("from") or item.get("into")) else 0
            # Mode-variant items use very large ids; prefer canonical low ids.
            canonical = 1 if item_id.isdigit() and int(item_id) < 220000 else 0
            return (on_sr, purchasable, has_path, canonical)

        candidates.sort(key=rank, reverse=True)
        return candidates[0][0]

    async def get_item_detail(self, item_name: str) -> dict[str, Any] | None:
        """Resolve an item by name and return its payload enriched with the
        display names of its build-path components (``from``/``into`` are ids).

        Returns ``None`` if the name cannot be resolved.
        """
        index = await self.get_item_index()
        item_id = self._resolve_item_id(index, item_name)
        if item_id is None:
            return None
        data = index.get("data", {})
        item = dict(data[item_id])
        item["_id"] = item_id
        item["_from_names"] = [data[i]["name"] for i in item.get("from", []) if i in data]
        item["_into_names"] = [data[i]["name"] for i in item.get("into", []) if i in data]
        return item

    # --- rune data ----------------------------------------------------------

    async def get_runes(self) -> list[dict[str, Any]]:
        """runesReforged.json — the rune trees (Precision, Domination, ...)."""
        version = await self.get_version()
        locale = self._config.ddragon_locale
        url = f"{DDRAGON_BASE}/cdn/{version}/data/{locale}/runesReforged.json"
        return await self._get_json(url, f"runes:{version}:{locale}")

    async def find_rune(self, rune_name: str) -> dict[str, Any] | None:
        """Find a single rune by name across all trees/slots. Returns the rune
        dict plus its tree name and whether it's a keystone, or ``None``."""
        query = "".join(c for c in rune_name.strip().lower() if c.isalnum())
        if not query:
            return None
        trees = await self.get_runes()
        for tree in trees:
            for slot_idx, slot in enumerate(tree.get("slots", [])):
                for rune in slot.get("runes", []):
                    name = "".join(c for c in rune.get("name", "").lower() if c.isalnum())
                    if name == query:
                        return {
                            **rune,
                            "_tree": tree.get("name", ""),
                            "_is_keystone": slot_idx == 0,
                        }
        return None
