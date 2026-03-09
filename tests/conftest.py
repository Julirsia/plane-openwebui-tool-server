from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.deps import get_plane_client, get_template_registry, get_transition_policy
from app.main import app
from app.renderer import render_ticket_html
from app.templates_registry import TemplateRegistry


class FakePlaneClient:
    def __init__(self) -> None:
        self.project = {"id": "project-1", "name": "Support", "identifier": "SUP"}
        self.states = [
            {"id": "state-new", "name": "New"},
            {"id": "state-triage", "name": "Triage"},
            {"id": "state-progress", "name": "In Progress"},
            {"id": "state-waiting", "name": "Waiting Customer"},
            {"id": "state-ready", "name": "Ready to Reply"},
            {"id": "state-resolved", "name": "Resolved"},
            {"id": "state-closed", "name": "Closed"},
        ]
        self.labels = [{"id": f"label-{name}", "name": name} for name in [
            "channel:email",
            "channel:chat",
            "channel:phone",
            "channel:manual",
            "kind:troubleshooting",
            "kind:howto",
            "kind:billing",
            "kind:feature",
            "product:auth",
            "product:api",
            "product:admin",
            "product:billing",
            "product:unknown",
            "severity:s1",
            "severity:s2",
            "severity:s3",
            "severity:s4",
            "customer:premium",
            "customer:standard",
            "customer:unknown",
            "comm:reply-needed",
            "comm:draft-ready",
            "comm:resolved-notified",
        ]]
        self.members = [
            {"id": "member-1", "display_name": "홍길동"},
            {"id": "member-2", "display_name": "김철수"},
        ]
        registry = TemplateRegistry(ROOT_DIR / "templates")
        template = registry.get("support.troubleshooting")
        attributes = {
            "customer_name": "ACME",
            "customer_org": "ACME Corp",
            "channel": "email",
            "product": "auth",
            "severity": "s2",
            "customer_tier": "standard",
            "priority": "high",
            "initial_state_name": "Triage",
            "assignee_name": "김철수",
        }
        content = {
            "short_summary": "로그인 루프",
            "current_summary": "SSO 고객에서 로그인 루프가 보고되었습니다.",
            "customer_symptom": "로그인 뒤 다시 로그인 화면으로 이동합니다.",
            "impact": "관리자 12명이 주문을 확인할 수 없습니다.",
            "environment": "Windows 11 / Chrome",
            "reproduction": "고객 환경에서 재현됨",
            "attempted_actions": "쿠키 삭제 후 재로그인",
            "confirmed_facts": "Chrome 과 Edge 에서 재현됩니다.",
            "open_questions": "비 SSO 고객 영향 여부는 미확인입니다.",
            "suspected_cause": "redirect 또는 session 문제 가능성",
            "next_actions_internal": "auth redirect diff 확인",
            "customer_reply_points": "현재 조사 중이며 추가 로그를 요청할 수 있습니다.",
            "resolution": "",
        }
        description_html = render_ticket_html(template, attributes, content, "홍길동")
        self.work_items = {
            "SUP-214": {
                "id": "wi-214",
                "identifier": "SUP-214",
                "name": "[auth][s2] 로그인 루프",
                "description_html": description_html,
                "state": {"id": "state-triage", "name": "Triage"},
                "priority": "high",
                "labels": [self._label("channel:email"), self._label("kind:troubleshooting"), self._label("product:auth"), self._label("severity:s2"), self._label("customer:standard")],
                "assignees": [self._member("김철수")],
                "updated_at": "2026-03-09T01:00:00+00:00",
            },
            "SUP-215": {
                "id": "wi-215",
                "identifier": "SUP-215",
                "name": "[auth][s3] 대시보드 지연",
                "description_html": description_html.replace("로그인 루프", "대시보드 지연"),
                "state": {"id": "state-progress", "name": "In Progress"},
                "priority": "medium",
                "labels": [self._label("channel:email"), self._label("kind:troubleshooting"), self._label("product:auth"), self._label("severity:s3"), self._label("customer:standard"), self._label("comm:reply-needed")],
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
                "labels": [self._label("kind:troubleshooting"), self._label("product:auth"), self._label("severity:s2")],
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
                    "comment_html": "<p><strong>[SUMMARY_REFRESH][by:홍길동]</strong></p><p>updated sections: current_summary</p>",
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

    async def list_work_items(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        self.list_work_items_calls.append({"limit": limit, "offset": offset, "expand": "labels,assignees,state"})
        items = sorted(self.work_items.values(), key=lambda item: item["updated_at"], reverse=True)
        end = offset + limit
        return {"results": deepcopy(items[offset:end])}

    async def create_work_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_tickets.append(deepcopy(payload))
        ticket = {
            "id": "wi-999",
            "identifier": "SUP-999",
            "name": payload["name"],
            "description_html": payload["description_html"],
            "state": {"id": payload["state"], "name": "Triage"},
            "priority": payload["priority"],
            "labels": [label for label in self.labels if label["id"] in payload["labels"]],
            "assignees": [member for member in self.members if member["id"] in payload["assignees"]],
            "updated_at": "2026-03-11T01:00:00+00:00",
        }
        self.work_items[ticket["identifier"]] = ticket
        return deepcopy(ticket)

    async def get_work_item_by_identifier(self, identifier: str) -> dict[str, Any]:
        self.identifier_lookup_calls.append(identifier)
        return deepcopy(self.work_items[identifier])

    async def update_work_item(self, work_item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.updated_payloads.append({"work_item_id": work_item_id, "payload": deepcopy(payload)})
        ticket = next(item for item in self.work_items.values() if item["id"] == work_item_id)
        if "description_html" in payload:
            ticket["description_html"] = payload["description_html"]
        if "state" in payload:
            state = next(item for item in self.states if item["id"] == payload["state"])
            ticket["state"] = deepcopy(state)
        if "labels" in payload:
            ticket["labels"] = [label for label in self.labels if label["id"] in payload["labels"]]
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
    registry = TemplateRegistry(ROOT_DIR / "templates")
    transition_policy = {
        "New": ["Triage"],
        "Triage": ["In Progress", "Waiting Customer", "Ready to Reply", "Resolved"],
        "In Progress": ["Waiting Customer", "Ready to Reply", "Resolved"],
        "Waiting Customer": ["In Progress", "Ready to Reply"],
        "Ready to Reply": ["Waiting Customer", "Resolved"],
        "Resolved": ["Closed", "In Progress"],
        "Closed": ["In Progress"],
    }
    app.dependency_overrides[get_plane_client] = lambda: fake_plane_client
    app.dependency_overrides[get_template_registry] = lambda: registry
    app.dependency_overrides[get_transition_policy] = lambda: transition_policy
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
