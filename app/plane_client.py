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
        self.workspace_api_url = (
            f"{str(settings.plane_base_url).rstrip('/')}/api/v1/workspaces/{settings.plane_workspace_slug}"
        )
        self.project_api_url = f"{self.workspace_api_url}/projects/{settings.plane_project_id}"
        self._client = httpx.AsyncClient(
            headers={"x-api-key": settings.plane_api_key, "Accept": "application/json"},
            timeout=float(settings.request_timeout_seconds),
        )
        self._cache = TTLCache[dict[str, Any]](settings.meta_cache_ttl_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    def _workspace_endpoint(self, path: str) -> str:
        return f"{self.workspace_api_url}{path}"

    def _project_endpoint(self, path: str) -> str:
        return f"{self.project_api_url}{path}"

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        attempts = 0
        while True:
            attempts += 1
            response = await self._client.request(method, url, **kwargs)
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
                logger.warning("Plane API error status=%s url=%s", response.status_code, url)
                raise HTTPException(status_code=502, detail=f"Plane API error: {detail}")
            if response.status_code == 204:
                return None
            return response.json()

    async def get_project(self) -> dict[str, Any]:
        cache_key = "project"
        if cached := self._cache.get(cache_key):
            return cached
        data = await self._request("GET", self._project_endpoint("/"))
        self._cache.set(cache_key, data)
        return data

    async def list_states(self) -> list[dict[str, Any]]:
        cache_key = "states"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", self._project_endpoint("/states/"))
        items = data.get("results", data if isinstance(data, list) else [])
        self._cache.set(cache_key, {"items": items})
        return items

    async def list_labels(self) -> list[dict[str, Any]]:
        cache_key = "labels"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", self._project_endpoint("/labels/"))
        items = data.get("results", data if isinstance(data, list) else [])
        self._cache.set(cache_key, {"items": items})
        return items

    async def list_project_members(self) -> list[dict[str, Any]]:
        cache_key = "members"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", self._project_endpoint("/members/"))
        items = data.get("results", data if isinstance(data, list) else [])
        self._cache.set(cache_key, {"items": items})
        return items

    async def list_work_items(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        state_id: str | None = None,
        assignee_id: str | None = None,
    ) -> dict[str, Any]:
        params = {"limit": limit, "offset": offset, "expand": "labels,assignees,state"}
        if state_id:
            params["state"] = state_id
        if assignee_id:
            params["assignee"] = assignee_id
        return await self._request("GET", self._project_endpoint("/work-items/"), params=params)

    async def create_work_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", self._project_endpoint("/work-items/"), json=payload)

    async def get_work_item_by_identifier(self, identifier: str) -> dict[str, Any]:
        params = {"expand": "labels,assignees,state,project"}
        return await self._request("GET", self._workspace_endpoint(f"/work-items/{identifier}/"), params=params)

    async def get_work_item_by_id(self, work_item_id: str) -> dict[str, Any]:
        params = {"expand": "labels,assignees,state,project"}
        return await self._request("GET", self._project_endpoint(f"/work-items/{work_item_id}/"), params=params)

    async def update_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", self._project_endpoint(f"/work-items/{work_item_id}/"), json=payload)

    async def list_comments(self, work_item_id: str, limit: int) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            self._project_endpoint(f"/work-items/{work_item_id}/comments/"),
            params={"limit": limit, "offset": 0},
        )
        return data.get("results", data if isinstance(data, list) else [])

    async def create_comment(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            self._project_endpoint(f"/work-items/{work_item_id}/comments/"),
            json=payload,
        )

    async def list_activities(self, work_item_id: str, limit: int) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            self._project_endpoint(f"/work-items/{work_item_id}/activities/"),
            params={"limit": limit, "offset": 0},
        )
        return data.get("results", data if isinstance(data, list) else [])


def parse_plane_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
