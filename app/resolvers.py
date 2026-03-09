from __future__ import annotations

import re
from datetime import datetime
from html import escape
from typing import Any

from bs4 import BeautifulSoup
from fastapi import HTTPException
from markdown_it import MarkdownIt

from app.config import Settings

md = MarkdownIt("commonmark", {"breaks": True})

STATE_ALIASES: dict[str, tuple[str, ...]] = {
    "triage": ("triage",),
    "in_progress": ("in progress", "in_progress", "in-progress", "wip"),
    "waiting_customer": ("waiting customer", "waiting_customer", "waiting-customer"),
    "ready_to_reply": ("ready to reply", "ready_to_reply", "ready-to-reply"),
    "resolved": ("resolved",),
    "closed": ("closed",),
}


def normalize_name(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.strip().lower())


def state_aliases_response() -> dict[str, list[str]]:
    return {key: list(values) for key, values in STATE_ALIASES.items()}


def state_key_from_name(state_name: str) -> str | None:
    normalized = normalize_name(state_name)
    for key, aliases in STATE_ALIASES.items():
        if normalized in {normalize_name(alias) for alias in aliases}:
            return key
    return None


def state_key_from_ticket(ticket: dict[str, Any]) -> str | None:
    return state_key_from_name(state_name(ticket))


def state_name(ticket: dict[str, Any]) -> str:
    raw_state = ticket.get("state")
    if isinstance(raw_state, dict):
        return raw_state.get("name", "")
    return str(ticket.get("state_name", "") or "")


def state_id(ticket: dict[str, Any]) -> str:
    raw_state = ticket.get("state")
    if isinstance(raw_state, dict):
        return raw_state.get("id", "")
    return str(ticket.get("state_id", "") or "")


def member_display_name(raw: dict[str, Any]) -> str:
    return str(raw.get("display_name") or raw.get("member", {}).get("display_name", "") or "")


def label_name(raw: dict[str, Any]) -> str:
    return str(raw.get("name") or "")


def ticket_assignee_names(ticket: dict[str, Any]) -> list[str]:
    return [member_display_name(item) for item in ticket.get("assignees") or [] if member_display_name(item)]


def ticket_assignee_ids(ticket: dict[str, Any]) -> list[str]:
    return [str(item.get("id")) for item in ticket.get("assignees") or [] if item.get("id")]


def ticket_label_names(ticket: dict[str, Any]) -> list[str]:
    return [label_name(item) for item in ticket.get("labels") or [] if label_name(item)]


def ticket_label_ids(ticket: dict[str, Any]) -> list[str]:
    return [str(item.get("id")) for item in ticket.get("labels") or [] if item.get("id")]


def html_to_text(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def text_to_html(value: str) -> str:
    parts = [line.strip() for line in value.splitlines()]
    return "".join(f"<p>{escape(line)}</p>" for line in parts if line)


def markdown_to_html(value: str) -> str:
    return md.render(value)


def parse_plane_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ensure_unmodified(expected_updated_at: datetime | None, actual_updated_at: datetime | None) -> None:
    if expected_updated_at is None or actual_updated_at is None:
        return
    if expected_updated_at != actual_updated_at:
        raise HTTPException(status_code=409, detail="Ticket was modified after the provided context")


def exact_name_map(items: list[dict[str, Any]], *, name_key: str = "name", id_key: str = "id") -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in items:
        raw_name = item.get(name_key)
        raw_id = item.get(id_key)
        if raw_name and raw_id:
            mapping[str(raw_name)] = str(raw_id)
    return mapping


def member_name_map(items: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in items:
        display_name = member_display_name(item)
        member_id = item.get("id")
        if display_name and member_id:
            mapping[display_name] = str(member_id)
    return mapping


def resolve_state_id(
    *,
    state_name_input: str | None,
    state_id_input: str | None,
    settings: Settings,
    runtime_states: list[dict[str, Any]],
) -> str | None:
    if state_id_input:
        return state_id_input
    if not state_name_input:
        return None
    if state_key := state_key_from_name(state_name_input):
        return settings.state_id_mapping[state_key]
    runtime_map = exact_name_map(runtime_states)
    if resolved := runtime_map.get(state_name_input):
        return resolved
    allowed = ", ".join(sorted(settings.state_id_mapping))
    raise HTTPException(status_code=400, detail=f"Unknown state name: {state_name_input}. Allowed keys: {allowed}")


def resolve_state_ids(
    *,
    state_names: list[str],
    state_ids: list[str],
    settings: Settings,
    runtime_states: list[dict[str, Any]],
) -> list[str]:
    resolved = list(state_ids)
    for item in state_names:
        resolved_id = resolve_state_id(
            state_name_input=item,
            state_id_input=None,
            settings=settings,
            runtime_states=runtime_states,
        )
        if resolved_id and resolved_id not in resolved:
            resolved.append(resolved_id)
    return resolved


def resolve_label_ids(
    *,
    label_names: list[str] | None,
    label_ids: list[str] | None,
    runtime_labels: list[dict[str, Any]],
) -> list[str] | None:
    if label_names is None and label_ids is None:
        return None
    resolved = list(label_ids or [])
    name_map = exact_name_map(runtime_labels)
    for label_name_input in label_names or []:
        label_id = name_map.get(label_name_input)
        if label_id is None:
            raise HTTPException(status_code=400, detail=f"Unknown label name: {label_name_input}")
        if label_id not in resolved:
            resolved.append(label_id)
    return resolved


def resolve_assignee_ids(
    *,
    assignee_names: list[str] | None,
    assignee_ids: list[str] | None,
    runtime_members: list[dict[str, Any]],
) -> list[str] | None:
    if assignee_names is None and assignee_ids is None:
        return None
    resolved = list(assignee_ids or [])
    name_map = member_name_map(runtime_members)
    for assignee_name_input in assignee_names or []:
        assignee_id = name_map.get(assignee_name_input)
        if assignee_id is None:
            raise HTTPException(status_code=400, detail=f"Unknown assignee name: {assignee_name_input}")
        if assignee_id not in resolved:
            resolved.append(assignee_id)
    return resolved


async def resolve_ticket_ref(
    *,
    plane_client: Any,
    identifier: str | None,
    work_item_id: str | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    if work_item_id:
        ticket = await plane_client.get_work_item_by_id(work_item_id)
        if identifier and ticket.get("identifier") != identifier:
            raise HTTPException(status_code=400, detail="Provided identifier does not match the provided id")
        return ticket, {"id": str(ticket["id"]), "identifier": str(ticket["identifier"]), "ref_type": "id"}
    ticket = await plane_client.get_work_item_by_identifier(str(identifier))
    return ticket, {"id": str(ticket["id"]), "identifier": str(ticket["identifier"]), "ref_type": "identifier"}


def search_text(ticket: dict[str, Any]) -> str:
    return " ".join(
        [
            str(ticket.get("identifier", "") or ""),
            str(ticket.get("name", "") or ""),
            html_to_text(str(ticket.get("description_html", "") or "")),
        ]
    ).lower()


def description_excerpt(ticket: dict[str, Any], limit: int = 240) -> str:
    return html_to_text(str(ticket.get("description_html", "") or ""))[:limit]
