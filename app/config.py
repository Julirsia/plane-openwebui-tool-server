from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl
from dotenv import load_dotenv


class Settings(BaseModel):
    plane_base_url: HttpUrl
    plane_workspace_slug: str
    plane_project_id: str
    plane_api_key: str
    default_language: str = "ko"
    default_timezone: str = "Asia/Seoul"
    context_cache_ttl_seconds: int = 60
    default_comment_limit: int = 30
    default_activity_limit: int = 30
    enforce_transition_policy: bool = False
    log_level: str = "INFO"
    root_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)

    @property
    def templates_dir(self) -> Path:
        return self.root_dir / "templates"

    @property
    def policies_dir(self) -> Path:
        return self.root_dir / "policies"


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    settings = Settings(
        plane_base_url=_env("PLANE_BASE_URL"),
        plane_workspace_slug=_env("PLANE_WORKSPACE_SLUG"),
        plane_project_id=_env("PLANE_PROJECT_ID"),
        plane_api_key=_env("PLANE_API_KEY"),
        default_language=_env("DEFAULT_LANGUAGE", "ko"),
        default_timezone=_env("DEFAULT_TIMEZONE", "Asia/Seoul"),
        context_cache_ttl_seconds=int(_env("CONTEXT_CACHE_TTL_SECONDS", "60")),
        default_comment_limit=int(_env("DEFAULT_COMMENT_LIMIT", "30")),
        default_activity_limit=int(_env("DEFAULT_ACTIVITY_LIMIT", "30")),
        enforce_transition_policy=_env("ENFORCE_TRANSITION_POLICY", "false").lower() == "true",
        log_level=_env("LOG_LEVEL", "INFO"),
    )
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    return settings
