from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.plane_client import PlaneClient
from app.policy import load_transition_policy
from app.templates_registry import TemplateRegistry


def get_app_settings() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def get_template_registry() -> TemplateRegistry:
    settings = get_settings()
    return TemplateRegistry(settings.templates_dir)


@lru_cache(maxsize=1)
def get_transition_policy() -> dict[str, list[str]]:
    settings = get_settings()
    return load_transition_policy(str(settings.policies_dir / "transition_policy.yaml"))


@lru_cache(maxsize=1)
def get_plane_client() -> PlaneClient:
    return PlaneClient(get_settings())
