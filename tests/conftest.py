from __future__ import annotations

from copy import deepcopy
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import Settings
from app.deps import get_app_settings, get_plane_client
from app.main import app


class FakePlaneClient:
    def __init__(self) -> None:
        self.project = {"id": "project-1", "name": "Support", "identifier": "SUP"}
        self.states = [
            {"id": "state-triage", "name": "Triage"},
            {"id": "state-progress", "name": "In Progress"},
            {"id": "state-waiting", "name": "Waiting Customer"},
            {"id": "state-ready", "name": "Ready to Reply"},
            {"id": "state-resolved", "name": "Resolved"},
            {"id": "state-closed", "name": "Closed"},
        ]
        self.labels = [
            {"id": "label-auth", "name": "product:auth", "color": "#ff0000"},
            {"id": "label-billing", "name": "product:billing", "color": "#00ff00"},
            {"id": "label-triage", "name": "queue:triage", "color": "#0000ff"},
        ]
        self.members = [
            {"id": "member-1", "display_name": "홍길동", "email": "hong@example.com"},
            {"id": "member-2", "display_name": "김철수", "email": "kim@example.com"},
        ]
        self.work_items = {
            "SUP-214": {
                "id": "wi-214",
                "identifier": "SUP-214",
                "name": "로그인 루프",
                "description_html": "<p>SSO 고객에서 로그인 루프가 보고되었습니다.</p><p>추가 로그 확인이 필요합니다.</p>",
                "state": {"id": "state-triage", "name": "Triage"},
                "priority": "high",
                "labels": [self._label("product:auth"), self._label("queue:triage")],
                "assignees": [self._member("김철수")],
                "updated_at": "2026-03-09T01:00:00+00:00",
            },
            "SUP-215": {
                "id": "wi-215",
                "identifier": "SUP-215",
                "name": "대시보드 지연",
                "description_html": "<p>관리자 대시보드 로딩이 느립니다.</p>",
                "state": {"id": "state-progress", "name": "In Progress"},
                "priority": "medium",
                "labels": [self._label("product:auth")],
                "assignees": [self._member("홍길동")],
                "updated_at": "2026-03-10T01:00:00+00:00",
            },
            "SOFT-170": {
                "id": "wi-170",
                "identifier": "SOFT-170",
                "name": "기존 티켓 포맷 로그인 오류",
                "description_html": "<p>고객이 로그인 오류를 제보했습니다.</p><p>SSO 설정 이후부터 발생했다고 합니다.</p>",
                "state": {"id": "state-progress", "name": "In Progress"},
                "priority": "high",
                "labels": [self._label("product:auth")],
                "assignees": [self._member("홍길동")],
                "updated_at": "2026-03-08T01:00:00+00:00",
            },
        }
        self.comments: dict[str, list[dict[str, Any]]] = {
            "wi-214": [
                {
                    "id": "comment-1",
                    "created_at": "2026-03-09T01:05:00+00:00",
                    "actor_detail": {"display_name": "홍길동"},
                    "access": "INTERNAL",
                    "comment_html": "<p>로그 확인 중</p>",
                }
            ],
            "wi-215": [],
            "wi-170": [],
        }
        self.activities = {
            "wi-214": [
                {
                    "id": "activity-1",
                    "created_at": "2026-03-09T01:01:00+00:00",
                    "verb": "updated",
                    "field": "state",
                    "old_value": "New",
                    "new_value": "Triage",
                }
            ],
            "wi-215": [],
            "wi-170": [],
        }
        self.created_comment_payloads: list[dict[str, Any]] = []
        self.updated_payloads: list[dict[str, Any]] = []
        self.created_tickets: list[dict[str, Any]] = []
        self.identifier_lookup_calls: list[str] = []
        self.id_lookup_calls: list[str] = []
        self.list_work_items_calls: list[dict[str, Any]] = []

    def _label(self, name: str) -> dict[str, Any]:
        return next(item for item in self.labels if item["name"] == name)

    def _member(self, display_name: str) -> dict[str, Any]:
        return next(item for item in self.members if item["display_name"] == display_name)

    async def close(self) -> None:
        return None

    async def get_project(self) -> dict[str, Any]:
        return deepcopy(self.project)

    async def list_states(self) -> list[dict[str, Any]]:
        return deepcopy(self.states)

    async def list_labels(self) -> list[dict[str, Any]]:
        return deepcopy(self.labels)

    async def list_project_members(self) -> list[dict[str, Any]]:
        return deepcopy(self.members)

    async def list_work_items(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        state_id: str | None = None,
        assignee_id: str | None = None,
    ) -> dict[str, Any]:
        self.list_work_items_calls.append(
            {
                "limit": limit,
                "offset": offset,
                "expand": "labels,assignees,state",
                "state": state_id,
                "assignee": assignee_id,
            }
        )
        items = sorted(self.work_items.values(), key=lambda item: item["updated_at"], reverse=True)
        if state_id:
            items = [item for item in items if item["state"]["id"] == state_id]
        if assignee_id:
            items = [item for item in items if any(member["id"] == assignee_id for member in item["assignees"])]
        end = offset + limit
        return {"results": deepcopy(items[offset:end])}

    async def create_work_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_tickets.append(deepcopy(payload))
        state_id = payload.get("state", "state-triage")
        label_ids = payload.get("labels", [])
        assignee_ids = payload.get("assignees", [])
        ticket = {
            "id": "wi-999",
            "identifier": "SUP-999",
            "name": payload["name"],
            "description_html": payload.get("description_html", ""),
            "state": next((deepcopy(item) for item in self.states if item["id"] == state_id), {"id": state_id, "name": "Triage"}),
            "priority": payload.get("priority"),
            "labels": [label for label in self.labels if label["id"] in label_ids],
            "assignees": [member for member in self.members if member["id"] in assignee_ids],
            "updated_at": "2026-03-11T01:00:00+00:00",
        }
        self.work_items[ticket["identifier"]] = ticket
        return deepcopy(ticket)

    async def get_work_item_by_identifier(self, identifier: str) -> dict[str, Any]:
        self.identifier_lookup_calls.append(identifier)
        return deepcopy(self.work_items[identifier])

    async def get_work_item_by_id(self, work_item_id: str) -> dict[str, Any]:
        self.id_lookup_calls.append(work_item_id)
        ticket = next(item for item in self.work_items.values() if item["id"] == work_item_id)
        return deepcopy(ticket)

    async def update_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.updated_payloads.append({"work_item_id": work_item_id, "payload": deepcopy(payload)})
        ticket = next(item for item in self.work_items.values() if item["id"] == work_item_id)
        if "name" in payload:
            ticket["name"] = payload["name"]
        if "description_html" in payload:
            ticket["description_html"] = payload["description_html"]
        if "state" in payload:
            state = next(item for item in self.states if item["id"] == payload["state"])
            ticket["state"] = deepcopy(state)
        if "priority" in payload:
            ticket["priority"] = payload["priority"]
        if "labels" in payload:
            ticket["labels"] = [label for label in self.labels if label["id"] in payload["labels"]]
        if "assignees" in payload:
            ticket["assignees"] = [member for member in self.members if member["id"] in payload["assignees"]]
        ticket["updated_at"] = "2026-03-11T02:00:00+00:00"
        return deepcopy(ticket)

    async def list_comments(self, work_item_id: str, limit: int) -> list[dict[str, Any]]:
        return deepcopy(self.comments.get(work_item_id, [])[:limit])

    async def create_comment(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_comment_payloads.append({"work_item_id": work_item_id, "payload": deepcopy(payload)})
        comment = {
            "id": f"comment-{len(self.created_comment_payloads)+1}",
            "created_at": "2026-03-11T02:00:00+00:00",
            "access": payload["access"],
            "comment_html": payload["comment_html"],
        }
        self.comments.setdefault(work_item_id, []).insert(0, comment)
        return deepcopy(comment)

    async def list_activities(self, work_item_id: str, limit: int) -> list[dict[str, Any]]:
        return deepcopy(self.activities.get(work_item_id, [])[:limit])


@pytest.fixture
def fake_plane_client() -> FakePlaneClient:
    return FakePlaneClient()


@pytest.fixture
def client(fake_plane_client: FakePlaneClient) -> TestClient:
    settings = Settings(
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
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_plane_client] = lambda: fake_plane_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
