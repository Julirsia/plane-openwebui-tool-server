from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.config import Settings
from app.plane_client import PlaneClient


def _settings() -> Settings:
    return Settings(
        plane_base_url="https://plane.example.com",
        plane_workspace_slug="my-workspace",
        plane_project_id="project-uuid",
        plane_api_key="plane_api_xxx",
    )


@pytest.mark.asyncio
async def test_get_work_item_by_identifier_uses_workspace_scoped_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "wi-214", "identifier": "SUP-214"})

    client = PlaneClient(_settings())
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    result = await client.get_work_item_by_identifier("SUP-214")

    assert result["id"] == "wi-214"
    assert requests[0].url.path == "/api/v1/workspaces/my-workspace/work-items/SUP-214/"
    assert requests[0].url.params["expand"] == "labels,assignees,state,project"
    await client.close()


@pytest.mark.asyncio
async def test_update_work_item_uses_project_scoped_uuid_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "wi-214"})

    client = PlaneClient(_settings())
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    await client.update_work_item("wi-214", {"state": "state-resolved"})

    assert requests[0].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/wi-214/"
    assert requests[0].read().decode() == '{"state":"state-resolved"}'
    await client.close()


@pytest.mark.asyncio
async def test_list_work_items_uses_limit_offset_and_expand() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    client = PlaneClient(_settings())
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    await client.list_work_items(limit=25, offset=50)

    assert requests[0].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/"
    assert dict(requests[0].url.params) == {
        "limit": "25",
        "offset": "50",
        "expand": "labels,assignees,state",
    }
    await client.close()
