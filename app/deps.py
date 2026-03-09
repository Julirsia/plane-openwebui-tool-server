from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.plane_client import PlaneClient


def get_app_settings() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def get_plane_client() -> PlaneClient:
    return PlaneClient(get_settings())
