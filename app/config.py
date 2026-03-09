from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, HttpUrl


class Settings(BaseModel):
    plane_base_url: HttpUrl
    plane_workspace_slug: str
    plane_project_id: str
    plane_api_key: str
    default_comment_access: Literal["INTERNAL", "EXTERNAL"] = "INTERNAL"
    default_comment_limit: int = 30
    default_activity_limit: int = 30
    meta_cache_ttl_seconds: int = 60
    request_timeout_seconds: int = 20
    log_level: str = "INFO"
    plane_state_id_triage: str
    plane_state_id_in_progress: str
    plane_state_id_waiting_customer: str
    plane_state_id_ready_to_reply: str
    plane_state_id_resolved: str
    plane_state_id_closed: str

    @property
    def state_id_mapping(self) -> dict[str, str]:
        return {
            "triage": self.plane_state_id_triage,
            "in_progress": self.plane_state_id_in_progress,
            "waiting_customer": self.plane_state_id_waiting_customer,
            "ready_to_reply": self.plane_state_id_ready_to_reply,
            "resolved": self.plane_state_id_resolved,
            "closed": self.plane_state_id_closed,
        }


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
        default_comment_access=_env("DEFAULT_COMMENT_ACCESS", "INTERNAL").upper(),
        default_comment_limit=int(_env("DEFAULT_COMMENT_LIMIT", "30")),
        default_activity_limit=int(_env("DEFAULT_ACTIVITY_LIMIT", "30")),
        meta_cache_ttl_seconds=int(_env("META_CACHE_TTL_SECONDS", "60")),
        request_timeout_seconds=int(_env("REQUEST_TIMEOUT_SECONDS", "20")),
        log_level=_env("LOG_LEVEL", "INFO"),
        plane_state_id_triage=_env("PLANE_STATE_ID_TRIAGE"),
        plane_state_id_in_progress=_env("PLANE_STATE_ID_IN_PROGRESS"),
        plane_state_id_waiting_customer=_env("PLANE_STATE_ID_WAITING_CUSTOMER"),
        plane_state_id_ready_to_reply=_env("PLANE_STATE_ID_READY_TO_REPLY"),
        plane_state_id_resolved=_env("PLANE_STATE_ID_RESOLVED"),
        plane_state_id_closed=_env("PLANE_STATE_ID_CLOSED"),
    )
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    return settings
