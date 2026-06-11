"""Runtime configuration loaded from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env if present. Riot keys never get hard-coded.
load_dotenv()


@dataclass(frozen=True)
class Config:
    # Riot API key. NOT required for Data Dragon (static champion data is a public
    # CDN), so get_champion_info works without it. It IS required for the live
    # match / Spectator tools added in the next step.
    riot_api_key: str | None

    # Riot regional routing host for account/match APIs (e.g. americas, europe, asia).
    riot_regional_host: str

    # Riot platform host for Spectator/live-game APIs (e.g. na1, euw1, kr).
    riot_platform_host: str

    # Data Dragon static data version. "latest" resolves at startup against the
    # versions manifest; pin a value (e.g. "15.11.1") for reproducibility.
    ddragon_version: str

    # UI/data language for Data Dragon payloads.
    ddragon_locale: str

    # TTL (seconds) for cached static Data Dragon payloads.
    cache_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            riot_api_key=os.getenv("RIOT_API_KEY"),
            riot_regional_host=os.getenv("RIOT_REGIONAL_HOST", "americas"),
            riot_platform_host=os.getenv("RIOT_PLATFORM_HOST", "na1"),
            ddragon_version=os.getenv("DDRAGON_VERSION", "latest"),
            ddragon_locale=os.getenv("DDRAGON_LOCALE", "en_US"),
            cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "3600")),
        )
