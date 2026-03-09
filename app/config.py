from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Literal, Optional
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
from pydantic import BaseModel, HttpUrl, model_validator


class Settings(BaseModel):
    plane_api_base_url: HttpUrl
    plane_workspace_slug: str
    plane_project_id: str
    plane_api_key: str
    default_comment_access: Literal["INTERNAL", "EXTERNAL"] = "INTERNAL"
    default_comment_limit: int = 30
    default_activity_limit: int = 30
    meta_cache_ttl_seconds: int = 60
    request_timeout_seconds: int = 20
    log_level: str = "INFO"
    plane_workspace_url: Optional[HttpUrl] = None

    @model_validator(mode="after")
    def validate_workspace_slug(self) -> "Settings":
        if not self.plane_workspace_slug.strip():
            raise ValueError("plane_workspace_slug must not be empty")
        return self


def _normalize_api_base_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    scheme = parsed.scheme or "https"
    host = parsed.netloc or parsed.path
    if host == "app.plane.so":
        host = "api.plane.so"
    return urlunparse((scheme, host, "", "", "", "")).rstrip("/")


def _infer_workspace_slug(raw_workspace_url: str) -> str:
    parsed = urlparse(raw_workspace_url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise RuntimeError("Could not infer PLANE_WORKSPACE_SLUG from PLANE_WORKSPACE_URL")
    return parts[0]


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    raw_workspace_url = os.getenv("PLANE_WORKSPACE_URL")
    raw_api_base_url = os.getenv("PLANE_API_BASE_URL") or os.getenv("PLANE_BASE_URL")
    if raw_workspace_url:
        workspace_slug = os.getenv("PLANE_WORKSPACE_SLUG") or _infer_workspace_slug(raw_workspace_url)
        api_base_url = raw_api_base_url or raw_workspace_url
    else:
        workspace_slug = _env("PLANE_WORKSPACE_SLUG")
        api_base_url = _env("PLANE_API_BASE_URL", os.getenv("PLANE_BASE_URL"))

    settings = Settings(
        plane_api_base_url=_normalize_api_base_url(api_base_url),
        plane_workspace_url=raw_workspace_url,
        plane_workspace_slug=workspace_slug,
        plane_project_id=_env("PLANE_PROJECT_ID"),
        plane_api_key=_env("PLANE_API_KEY"),
        default_comment_access=_env("DEFAULT_COMMENT_ACCESS", "INTERNAL").upper(),
        default_comment_limit=int(_env("DEFAULT_COMMENT_LIMIT", "30")),
        default_activity_limit=int(_env("DEFAULT_ACTIVITY_LIMIT", "30")),
        meta_cache_ttl_seconds=int(_env("META_CACHE_TTL_SECONDS", "60")),
        request_timeout_seconds=int(_env("REQUEST_TIMEOUT_SECONDS", "20")),
        log_level=_env("LOG_LEVEL", "INFO"),
    )
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    return settings
