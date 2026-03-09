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
        default_comment_access="INTERNAL",
        default_comment_limit=30,
        default_activity_limit=30,
        meta_cache_ttl_seconds=60,
        request_timeout_seconds=20,
        plane_state_id_triage="state-triage",
        plane_state_id_in_progress="state-progress",
        plane_state_id_waiting_customer="state-waiting",
        plane_state_id_ready_to_reply="state-ready",
        plane_state_id_resolved="state-resolved",
        plane_state_id_closed="state-closed",
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
async def test_get_work_item_by_id_uses_project_scoped_uuid_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "wi-214"})

    client = PlaneClient(_settings())
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    await client.get_work_item_by_id("wi-214")

    assert requests[0].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/wi-214/"
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
async def test_list_work_items_uses_limit_offset_expand_and_filters() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    client = PlaneClient(_settings())
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    await client.list_work_items(limit=25, offset=50, state_id="state-triage", assignee_id="member-1")

    assert requests[0].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/"
    assert dict(requests[0].url.params) == {
        "limit": "25",
        "offset": "50",
        "expand": "labels,assignees,state",
        "state": "state-triage",
        "assignee": "member-1",
    }
    await client.close()


@pytest.mark.asyncio
async def test_list_comments_and_activities_use_project_scoped_uuid_endpoints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    client = PlaneClient(_settings())
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    await client.list_comments("wi-214", 10)
    await client.list_activities("wi-214", 10)

    assert requests[0].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/wi-214/comments/"
    assert requests[1].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/wi-214/activities/"
    await client.close()
