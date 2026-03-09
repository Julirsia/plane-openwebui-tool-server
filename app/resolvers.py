from __future__ import annotations

import re
from datetime import datetime
from html import escape
from typing import Any

from bs4 import BeautifulSoup
from fastapi import HTTPException
from markdown_it import MarkdownIt

from app.models import StateGroup

md = MarkdownIt("commonmark", {"breaks": True})
ALLOWED_STATE_GROUPS: tuple[StateGroup, ...] = ("backlog", "unstarted", "started", "completed", "cancelled")


def normalize_name(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.strip().lower())


def state_group_value(raw: dict[str, Any]) -> StateGroup | None:
    group = raw.get("group")
    if group in ALLOWED_STATE_GROUPS:
        return group
    return None


def state_aliases_for_item(raw: dict[str, Any]) -> list[str]:
    state_name_value = str(raw.get("name", "") or "").strip()
    if not state_name_value:
        return []
    normalized = normalize_name(state_name_value)
    aliases = [
        state_name_value,
        state_name_value.lower(),
        normalized,
        normalized.replace(" ", "_"),
        normalized.replace(" ", "-"),
    ]
    seen: set[str] = set()
    unique_aliases: list[str] = []
    for alias in aliases:
        if alias and alias not in seen:
            seen.add(alias)
            unique_aliases.append(alias)
    return unique_aliases


def state_name(ticket: dict[str, Any]) -> str:
    raw_state = ticket.get("state")
    if isinstance(raw_state, dict):
        return str(raw_state.get("name", "") or "")
    return str(ticket.get("state_name", "") or "")


def state_id(ticket: dict[str, Any]) -> str:
    raw_state = ticket.get("state")
    if isinstance(raw_state, dict):
        return str(raw_state.get("id", "") or "")
    return str(ticket.get("state_id", "") or "")


def state_group(ticket: dict[str, Any]) -> StateGroup | None:
    raw_state = ticket.get("state")
    if isinstance(raw_state, dict):
        return state_group_value(raw_state)
    group = ticket.get("state_group")
    if group in ALLOWED_STATE_GROUPS:
        return group
    return None


def ticket_identifier(ticket: dict[str, Any]) -> str:
    if ticket.get("identifier"):
        return str(ticket["identifier"])
    project = ticket.get("project")
    project_identifier = ""
    if isinstance(project, dict):
        project_identifier = str(project.get("identifier", "") or "")
    sequence_id = ticket.get("sequence_id")
    if project_identifier and sequence_id is not None:
        return f"{project_identifier}-{sequence_id}"
    return ""


def member_display_name(raw: dict[str, Any]) -> str:
    return str(
        raw.get("display_name")
        or raw.get("member", {}).get("display_name", "")
        or " ".join(part for part in [raw.get("first_name"), raw.get("last_name")] if part).strip()
        or raw.get("email", "")
        or ""
    )


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


def _state_candidates_for_group(runtime_states: list[dict[str, Any]], target_group: StateGroup) -> list[dict[str, Any]]:
    return [item for item in runtime_states if state_group_value(item) == target_group]


def _state_candidates_for_name(runtime_states: list[dict[str, Any]], raw_name: str) -> list[dict[str, Any]]:
    exact = [item for item in runtime_states if str(item.get("name", "")) == raw_name]
    if exact:
        return exact
    normalized = normalize_name(raw_name)
    matches: list[dict[str, Any]] = []
    for item in runtime_states:
        if normalized in {normalize_name(alias) for alias in state_aliases_for_item(item)}:
            matches.append(item)
    return matches


def _state_candidate_summary(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "id": str(item.get("id", "")),
            "name": str(item.get("name", "")),
            "group": str(item.get("group", "")),
        }
        for item in items
    ]


def resolve_state_id(
    *,
    state_name_input: str | None,
    state_id_input: str | None,
    state_group_input: StateGroup | None,
    runtime_states: list[dict[str, Any]],
) -> str | None:
    if state_id_input:
        return state_id_input
    if state_name_input:
        candidates = _state_candidates_for_name(runtime_states, state_name_input)
        if len(candidates) == 1:
            return str(candidates[0]["id"])
        if len(candidates) > 1:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Ambiguous state name: {state_name_input}",
                    "candidates": _state_candidate_summary(candidates),
                },
            )
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Unknown state name: {state_name_input}",
                "available_states": _state_candidate_summary(runtime_states),
            },
        )
    if state_group_input:
        candidates = _state_candidates_for_group(runtime_states, state_group_input)
        if len(candidates) == 1:
            return str(candidates[0]["id"])
        if len(candidates) > 1:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"State group '{state_group_input}' is ambiguous in this project.",
                    "candidates": _state_candidate_summary(candidates),
                },
            )
        raise HTTPException(
            status_code=400,
            detail={"message": f"Unknown state group: {state_group_input}", "available_groups": list(ALLOWED_STATE_GROUPS)},
        )
    return None


def resolve_state_ids(
    *,
    state_name: str | None,
    state_id_input: str | None,
    state_group_input: StateGroup | None,
    runtime_states: list[dict[str, Any]],
) -> list[str]:
    resolved = resolve_state_id(
        state_name_input=state_name,
        state_id_input=state_id_input,
        state_group_input=state_group_input,
        runtime_states=runtime_states,
    )
    return [resolved] if resolved else []


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
        resolved_identifier = ticket_identifier(ticket)
        if identifier and resolved_identifier != identifier:
            raise HTTPException(status_code=400, detail="Provided identifier does not match the provided id")
        return ticket, {"id": str(ticket["id"]), "identifier": resolved_identifier, "ref_type": "id"}
    ticket = await plane_client.get_work_item_by_identifier(str(identifier))
    return ticket, {"id": str(ticket["id"]), "identifier": ticket_identifier(ticket), "ref_type": "identifier"}


def search_text(ticket: dict[str, Any]) -> str:
    return " ".join(
        [
            ticket_identifier(ticket),
            str(ticket.get("name", "") or ""),
            html_to_text(str(ticket.get("description_html", "") or "")),
        ]
    ).lower()


def description_excerpt(ticket: dict[str, Any], limit: int = 240) -> str:
    raw_text = html_to_text(str(ticket.get("description_html", "") or ""))
    return raw_text[:limit]
