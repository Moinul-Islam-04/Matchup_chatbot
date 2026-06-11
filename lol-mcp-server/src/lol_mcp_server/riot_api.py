"""Live Riot API client (Account-V1 + Spectator-V5).

Two-step flow for a live match:
  1. Resolve a Riot ID ("gameName#tagLine") -> PUUID via Account-V1 on the
     *regional* routing host (americas/europe/asia).
  2. Fetch the active game for that PUUID via Spectator-V5 on the *platform*
     host (na1/euw1/kr/...).

Riot keys are required here (unlike Data Dragon). We surface the common failure
modes — expired/invalid key (403), not currently in a game (404), rate limit
(429) — as typed exceptions so the tool layer can return clean guidance to the
model instead of a raw stack trace.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Config
from .logging_setup import get_logger

log = get_logger("riot_api")


class RiotApiError(Exception):
    """Base class for Riot API failures with a user-facing message."""


class RiotAuthError(RiotApiError):
    """Missing/invalid/expired API key (401/403)."""


class RiotNotFoundError(RiotApiError):
    """Resource not found — unknown Riot ID, or summoner not in a live game (404)."""


class RiotRateLimitError(RiotApiError):
    """Rate limit exceeded (429)."""


class RiotClient:
    def __init__(self, config: Config, client: httpx.AsyncClient | None = None):
        self._config = config
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _require_key(self) -> str:
        key = self._config.riot_api_key
        if not key:
            raise RiotAuthError(
                "RIOT_API_KEY is not set. Add it to .env (dev keys expire every 24h)."
            )
        return key

    async def _get(self, host: str, path: str) -> Any:
        url = f"https://{host}.api.riotgames.com{path}"
        headers = {"X-Riot-Token": self._require_key()}
        log.info("GET %s", url)
        resp = await self._client.get(url, headers=headers)
        if resp.status_code in (401, 403):
            raise RiotAuthError(
                "Riot API rejected the key (expired or invalid). "
                "Regenerate it at https://developer.riotgames.com/."
            )
        if resp.status_code == 404:
            raise RiotNotFoundError("Riot API returned 404 (not found).")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "?")
            raise RiotRateLimitError(f"Rate limited by Riot. Retry after {retry}s.")
        resp.raise_for_status()
        return resp.json()

    async def get_account_by_riot_id(self, game_name: str, tag_line: str) -> dict[str, Any]:
        """Resolve "gameName#tagLine" -> account record (contains puuid)."""
        tag = tag_line.lstrip("#").strip()
        path = f"/riot/account/v1/accounts/by-riot-id/{game_name.strip()}/{tag}"
        try:
            return await self._get(self._config.riot_regional_host, path)
        except RiotNotFoundError:
            raise RiotNotFoundError(
                f"No Riot account found for '{game_name}#{tag}'. "
                "Check spelling, tag line, and that RIOT_REGIONAL_HOST matches the region."
            ) from None

    async def get_active_game_by_puuid(self, puuid: str) -> dict[str, Any]:
        """Fetch the in-progress game for a PUUID via Spectator-V5."""
        path = f"/lol/spectator/v5/active-games/by-summoner/{puuid}"
        try:
            return await self._get(self._config.riot_platform_host, path)
        except RiotNotFoundError:
            raise RiotNotFoundError(
                "That summoner is not currently in a live game "
                "(or the game just started/ended)."
            ) from None
