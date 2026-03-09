from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx
from fastapi import HTTPException

from app.cache import TTLCache
from app.config import Settings

logger = logging.getLogger(__name__)


class PlaneClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_api_url = (
            f"{str(settings.plane_base_url).rstrip('/')}/api/v1/workspaces/"
            f"{settings.plane_workspace_slug}/projects/{settings.plane_project_id}"
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_api_url,
            headers={"x-api-key": settings.plane_api_key, "Accept": "application/json"},
            timeout=20.0,
        )
        self._cache = TTLCache[dict[str, Any]](settings.context_cache_ttl_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        attempts = 0
        while True:
            attempts += 1
            response = await self._client.request(method, path, **kwargs)
            if response.status_code in {429, 500, 502, 503, 504} and attempts < 4:
                await asyncio.sleep(0.3 * (2 ** (attempts - 1)))
                continue
            if response.is_error:
                detail = response.text
                try:
                    body = response.json()
                    detail = body.get("detail") or body.get("message") or detail
                except Exception:
                    pass
                logger.warning("Plane API error status=%s path=%s", response.status_code, path)
                raise HTTPException(status_code=502, detail=f"Plane API error: {detail}")
            if response.status_code == 204:
                return None
            return response.json()

    async def get_project(self) -> dict[str, Any]:
        cache_key = "project"
        if cached := self._cache.get(cache_key):
            return cached
        data = await self._request("GET", "")
        self._cache.set(cache_key, data)
        return data

    async def list_states(self) -> list[dict[str, Any]]:
        cache_key = "states"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", "/states/")
        items = data.get("results", data if isinstance(data, list) else [])
        self._cache.set(cache_key, {"items": items})
        return items

    async def list_labels(self) -> list[dict[str, Any]]:
        cache_key = "labels"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", "/labels/")
        items = data.get("results", data if isinstance(data, list) else [])
        self._cache.set(cache_key, {"items": items})
        return items

    async def list_project_members(self) -> list[dict[str, Any]]:
        cache_key = "members"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", "/members/")
        items = data.get("results", data if isinstance(data, list) else [])
        self._cache.set(cache_key, {"items": items})
        return items

    async def list_work_items(self, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        params = {"page": page, "page_size": page_size}
        return await self._request("GET", "/work-items/", params=params)

    async def create_work_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/work-items/", json=payload)

    async def get_work_item_by_identifier(self, identifier: str) -> dict[str, Any]:
        return await self._request("GET", f"/work-items/{identifier}/", params={"expand": "labels,assignees,state"})

    async def update_work_item(self, identifier: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", f"/work-items/{identifier}/", json=payload)

    async def list_comments(self, work_item_id: str, limit: int) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/work-items/{work_item_id}/comments/", params={"page_size": limit})
        return data.get("results", data if isinstance(data, list) else [])

    async def create_comment(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/work-items/{work_item_id}/comments/", json=payload)

    async def list_activities(self, work_item_id: str, limit: int) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/work-items/{work_item_id}/activities/", params={"page_size": limit})
        return data.get("results", data if isinstance(data, list) else [])


def parse_plane_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
