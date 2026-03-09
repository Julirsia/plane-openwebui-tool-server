from __future__ import annotations

import httpx
import pytest

from app.config import Settings, _infer_workspace_slug, _normalize_api_base_url
from app.plane_client import PlaneClient


def _settings() -> Settings:
    return Settings(
        plane_api_base_url="https://plane.example.com",
        plane_workspace_url=None,
        plane_workspace_slug="my-workspace",
        plane_project_id="project-uuid",
        plane_api_key="plane_api_xxx",
        default_comment_access="INTERNAL",
        default_comment_limit=30,
        default_activity_limit=30,
        meta_cache_ttl_seconds=60,
        request_timeout_seconds=20,
        log_level="INFO",
    )


def _project_list_response() -> dict[str, object]:
    return {
        "results": [
            {
                "id": "project-uuid",
                "identifier": "TESTP",
                "name": "My Project",
            }
        ]
    }


def test_normalize_api_base_url_maps_plane_cloud_ui_host_to_api_host() -> None:
    assert _normalize_api_base_url("https://app.plane.so/test-workspace/") == "https://api.plane.so"


def test_normalize_api_base_url_keeps_self_hosted_origin() -> None:
    assert _normalize_api_base_url("https://plane.company.internal") == "https://plane.company.internal"


def test_infer_workspace_slug_reads_first_path_segment() -> None:
    assert _infer_workspace_slug("https://app.plane.so/test-plane-workspace-koh/") == "test-plane-workspace-koh"


@pytest.mark.asyncio
async def test_get_work_item_by_identifier_uses_workspace_scoped_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "wi-214", "identifier": "SUP-214"})

    client = PlaneClient(_settings())
    client._resolved_project_id = "project-uuid"
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
    client._resolved_project_id = "project-uuid"
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
    client._resolved_project_id = "project-uuid"
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    await client.update_work_item("wi-214", {"state": "state-done"})

    assert requests[0].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/wi-214/"
    assert requests[0].read().decode() == '{"state":"state-done"}'
    await client.close()


@pytest.mark.asyncio
async def test_list_work_items_uses_limit_offset_expand_and_filters() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    client = PlaneClient(_settings())
    client._resolved_project_id = "project-uuid"
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    await client.list_work_items(limit=25, offset=50, state_id="state-backlog", assignee_id="member-1")

    assert requests[0].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/"
    assert dict(requests[0].url.params) == {
        "limit": "25",
        "offset": "50",
        "expand": "labels,assignees,state,project",
        "state": "state-backlog",
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
    client._resolved_project_id = "project-uuid"
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    await client.list_comments("wi-214", 10)
    await client.list_activities("wi-214", 10)

    assert requests[0].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/wi-214/comments/"
    assert requests[1].url.path == "/api/v1/workspaces/my-workspace/projects/project-uuid/work-items/wi-214/activities/"
    await client.close()


@pytest.mark.asyncio
async def test_probe_meta_access_calls_project_and_runtime_meta_endpoints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/projects/"):
            return httpx.Response(200, json=_project_list_response())
        if request.url.path.endswith("/projects/project-uuid/"):
            return httpx.Response(200, json={"id": "project-uuid"})
        return httpx.Response(200, json={"results": []})

    client = PlaneClient(_settings())
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    result = await client.probe_meta_access()

    assert result["ok"] is True
    assert [request.url.path for request in requests] == [
        "/api/v1/workspaces/my-workspace/projects/",
        "/api/v1/workspaces/my-workspace/projects/project-uuid/",
        "/api/v1/workspaces/my-workspace/projects/project-uuid/states/",
        "/api/v1/workspaces/my-workspace/projects/project-uuid/labels/",
        "/api/v1/workspaces/my-workspace/projects/project-uuid/members/",
    ]
    await client.close()


@pytest.mark.asyncio
async def test_project_identifier_is_auto_resolved_before_project_scoped_calls() -> None:
    requests: list[httpx.Request] = []

    settings = Settings(
        plane_api_base_url="https://plane.example.com",
        plane_workspace_url=None,
        plane_workspace_slug="my-workspace",
        plane_project_id="TESTP",
        plane_api_key="plane_api_xxx",
        default_comment_access="INTERNAL",
        default_comment_limit=30,
        default_activity_limit=30,
        meta_cache_ttl_seconds=60,
        request_timeout_seconds=20,
        log_level="INFO",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/projects/"):
            return httpx.Response(200, json=_project_list_response())
        if request.url.path.endswith("/projects/project-uuid/states/"):
            return httpx.Response(200, json={"results": []})
        raise AssertionError(f"Unexpected path: {request.url.path}")

    client = PlaneClient(settings)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=client._client.headers)

    await client.list_states()

    assert [request.url.path for request in requests] == [
        "/api/v1/workspaces/my-workspace/projects/",
        "/api/v1/workspaces/my-workspace/projects/project-uuid/states/",
    ]
    await client.close()
