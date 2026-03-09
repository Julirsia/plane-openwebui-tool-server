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
        self.api_v1_url = f"{str(settings.plane_api_base_url).rstrip('/')}/api/v1"
        self.workspace_api_url = f"{self.api_v1_url}/workspaces/{settings.plane_workspace_slug}"
        self._client = httpx.AsyncClient(
            headers={"x-api-key": settings.plane_api_key, "Accept": "application/json"},
            timeout=float(settings.request_timeout_seconds),
        )
        self._cache = TTLCache[dict[str, Any]](settings.meta_cache_ttl_seconds)
        self._probe_ok = False
        self._resolved_project_id: str | None = None

    async def close(self) -> None:
        await self._client.aclose()

    def _workspace_endpoint(self, path: str) -> str:
        return f"{self.workspace_api_url}{path}"

    async def _project_endpoint(self, path: str) -> str:
        project_id = await self._project_id()
        return f"{self.workspace_api_url}/projects/{project_id}{path}"

    def _normalize_items(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            raw_items = data.get("results")
            if isinstance(raw_items, list):
                return raw_items
        return []

    def _error_hint(self, response: httpx.Response) -> str:
        host = response.request.url.host or ""
        if response.status_code in {401, 403}:
            return "Check PLANE_API_KEY permissions or auth header handling on the Plane server."
        if response.status_code == 404:
            if host == "app.plane.so":
                return "The UI host was used instead of the API host. Use api.plane.so or set PLANE_WORKSPACE_URL and let the server normalize it."
            return "Check workspace slug, project id, or whether the self-hosted Plane path differs from /api/v1."
        if response.status_code >= 500:
            return "The Plane server returned an upstream error. Check self-hosted logs and reverse proxy routing."
        return "Check PLANE_API_BASE_URL, PLANE_WORKSPACE_URL, PLANE_WORKSPACE_SLUG, and PLANE_PROJECT_ID."

    async def list_projects(self) -> list[dict[str, Any]]:
        cache_key = "projects"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", self._workspace_endpoint("/projects/"))
        items = self._normalize_items(data)
        self._cache.set(cache_key, {"items": items})
        return items

    async def _project_id(self) -> str:
        if self._resolved_project_id:
            return self._resolved_project_id
        lookup = self.settings.plane_project_id
        projects = await self.list_projects()
        for project in projects:
            if lookup in {
                str(project.get("id", "") or ""),
                str(project.get("identifier", "") or ""),
                str(project.get("name", "") or ""),
            }:
                self._resolved_project_id = str(project["id"])
                return self._resolved_project_id
        raise HTTPException(
            status_code=502,
            detail=(
                f"Plane project could not be resolved from PLANE_PROJECT_ID={lookup}. "
                "Use the project UUID, identifier, or exact project name."
            ),
        )

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
                hint = self._error_hint(response)
                raise HTTPException(status_code=502, detail=f"Plane API error: {detail} Hint: {hint}")
            if response.status_code == 204:
                return None
            return response.json()

    async def probe_meta_access(self) -> dict[str, Any]:
        if self._probe_ok:
            return {"ok": True}
        try:
            project = await self.get_project()
            states = await self.list_states()
            labels = await self.list_labels()
            members = await self.list_project_members()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Plane API probe failed. Check host, path, auth, and config. "
                    f"base={self.api_v1_url} workspace={self.settings.plane_workspace_slug} "
                    f"project={self.settings.plane_project_id} error={exc}"
                ),
            ) from exc

        if not isinstance(project, dict):
            raise HTTPException(status_code=502, detail="Plane API probe failed: project response was not an object.")
        if not isinstance(states, list):
            raise HTTPException(status_code=502, detail="Plane API probe failed: states response was not a list.")
        if not isinstance(labels, list):
            raise HTTPException(status_code=502, detail="Plane API probe failed: labels response was not a list.")
        if not isinstance(members, list):
            raise HTTPException(status_code=502, detail="Plane API probe failed: members response was not a list.")
        self._probe_ok = True
        return {
            "ok": True,
            "counts": {
                "states": len(states),
                "labels": len(labels),
                "members": len(members),
            },
        }

    async def get_project(self) -> dict[str, Any]:
        cache_key = "project"
        if cached := self._cache.get(cache_key):
            return cached
        data = await self._request("GET", await self._project_endpoint("/"))
        self._cache.set(cache_key, data)
        return data

    async def list_states(self) -> list[dict[str, Any]]:
        cache_key = "states"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", await self._project_endpoint("/states/"))
        items = self._normalize_items(data)
        self._cache.set(cache_key, {"items": items})
        return items

    async def list_labels(self) -> list[dict[str, Any]]:
        cache_key = "labels"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", await self._project_endpoint("/labels/"))
        items = self._normalize_items(data)
        self._cache.set(cache_key, {"items": items})
        return items

    async def list_project_members(self) -> list[dict[str, Any]]:
        cache_key = "members"
        if cached := self._cache.get(cache_key):
            return cached["items"]
        data = await self._request("GET", await self._project_endpoint("/members/"))
        items = self._normalize_items(data)
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
        params = {"limit": limit, "offset": offset, "expand": "labels,assignees,state,project"}
        if state_id:
            params["state"] = state_id
        if assignee_id:
            params["assignee"] = assignee_id
        return await self._request("GET", await self._project_endpoint("/work-items/"), params=params)

    async def create_work_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", await self._project_endpoint("/work-items/"), json=payload)

    async def get_work_item_by_identifier(self, identifier: str) -> dict[str, Any]:
        params = {"expand": "labels,assignees,state,project"}
        return await self._request("GET", self._workspace_endpoint(f"/work-items/{identifier}/"), params=params)

    async def get_work_item_by_id(self, work_item_id: str) -> dict[str, Any]:
        params = {"expand": "labels,assignees,state,project"}
        return await self._request("GET", await self._project_endpoint(f"/work-items/{work_item_id}/"), params=params)

    async def update_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", await self._project_endpoint(f"/work-items/{work_item_id}/"), json=payload)

    async def list_comments(self, work_item_id: str, limit: int) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            await self._project_endpoint(f"/work-items/{work_item_id}/comments/"),
            params={"limit": limit, "offset": 0},
        )
        return self._normalize_items(data)

    async def create_comment(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            await self._project_endpoint(f"/work-items/{work_item_id}/comments/"),
            json=payload,
        )

    async def list_activities(self, work_item_id: str, limit: int) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            await self._project_endpoint(f"/work-items/{work_item_id}/activities/"),
            params={"limit": limit, "offset": 0},
        )
        return self._normalize_items(data)


def parse_plane_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
