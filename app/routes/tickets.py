from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from markdown_it import MarkdownIt

from app.deps import get_app_settings, get_plane_client, get_template_registry, get_transition_policy
from app.models import (
    ActivityItem,
    CreateTicketRequest,
    CreateTicketResponse,
    InternalNote,
    SaveEmailDraftRequest,
    SaveEmailDraftResponse,
    SearchTicketsRequest,
    SearchTicketsResponse,
    TicketContextResponse,
    TicketSearchItem,
    TransitionRequest,
    TransitionResponse,
    UpsertSectionsRequest,
    UpsertSectionsResponse,
)
from app.parser import html_to_text, parse_note_type, parse_ticket_sections, upsert_ticket_sections
from app.plane_client import parse_plane_datetime
from app.policy import (
    allowed_next_states,
    ensure_editable_sections,
    ensure_unmodified,
    key_labels,
    map_names_to_ids,
    normalize_attributes,
    replace_comm_label,
    validate_labels_exist,
    validate_required_sections,
    validate_state_transition,
)
from app.renderer import render_ticket_html, render_title

router = APIRouter(prefix="/tickets", tags=["tickets"])
md = MarkdownIt("commonmark", {"breaks": True})


def _member_display_name(raw: dict[str, Any]) -> str:
    return raw.get("display_name") or raw.get("member", {}).get("display_name", "")


def _label_name(raw: dict[str, Any]) -> str:
    return raw.get("name", "")


def _state_name(ticket: dict[str, Any]) -> str:
    state = ticket.get("state")
    if isinstance(state, dict):
        return state.get("name", "")
    return ticket.get("state_name", "")


def _ticket_label_names(ticket: dict[str, Any]) -> list[str]:
    labels = ticket.get("labels") or []
    return [_label_name(label) for label in labels if _label_name(label)]


def _ticket_assignee_names(ticket: dict[str, Any]) -> list[str]:
    assignees = ticket.get("assignees") or []
    return [_member_display_name(item) for item in assignees if _member_display_name(item)]


def _parse_customer_org(sections: dict[str, str]) -> str:
    context = sections.get("customer_context", "")
    for line in context.splitlines():
        if line.startswith("고객사:"):
            return line.split(":", 1)[1].strip()
    return ""


def _build_note_html(header: str, body_lines: list[str]) -> str:
    body_html = "".join(f"<p>{escape(line)}</p>" for line in body_lines if line)
    return f"<p><strong>{escape(header)}</strong></p>{body_html}"


async def _context_maps(plane_client) -> dict[str, Any]:
    states = await plane_client.list_states()
    labels = await plane_client.list_labels()
    members = await plane_client.list_project_members()
    return {
        "state_names_to_ids": {item["name"]: item["id"] for item in states},
        "label_names_to_ids": {item["name"]: item["id"] for item in labels},
        "members_by_name": {_member_display_name(item): item["id"] for item in members if _member_display_name(item)},
    }


def _detect_template_id(sections: dict[str, str]) -> str:
    ticket_meta = sections.get("ticket_meta", "")
    lines = [line.strip() for line in ticket_meta.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        if "template_id" in line:
            if ":" in line:
                _, value = line.split(":", 1)
                if value.strip():
                    return value.strip()
            if idx + 1 < len(lines):
                return lines[idx + 1].lstrip(": ").strip()
    raise HTTPException(status_code=400, detail="Ticket template_id not found in ticket_meta")


def _search_match(ticket: dict[str, Any], sections: dict[str, str], payload: SearchTicketsRequest) -> bool:
    if payload.state_names and _state_name(ticket) not in payload.state_names:
        return False
    if payload.assignee_name and payload.assignee_name not in _ticket_assignee_names(ticket):
        return False
    label_names = set(_ticket_label_names(ticket))
    if payload.label_names and not set(payload.label_names).issubset(label_names):
        return False
    updated_at = parse_plane_datetime(ticket.get("updated_at"))
    if payload.updated_after and (updated_at is None or updated_at < payload.updated_after):
        return False
    if payload.updated_before and (updated_at is None or updated_at > payload.updated_before):
        return False
    if payload.text_query:
        haystack = " ".join(
            [
                ticket.get("identifier", ""),
                ticket.get("name", ""),
                sections.get("current_summary", ""),
                sections.get("customer_symptom", ""),
                sections.get("confirmed_facts", ""),
            ]
        ).lower()
        if payload.text_query.lower() not in haystack:
            return False
    return True


def _search_item(ticket: dict[str, Any], sections: dict[str, str], transition_policy: dict[str, list[str]]) -> TicketSearchItem:
    state_name = _state_name(ticket)
    return TicketSearchItem(
        identifier=ticket["identifier"],
        title=ticket.get("name", ""),
        state_name=state_name,
        priority=ticket.get("priority"),
        assignee_names=_ticket_assignee_names(ticket),
        key_labels=key_labels(_ticket_label_names(ticket)),
        updated_at=parse_plane_datetime(ticket.get("updated_at")),
        current_summary_excerpt=sections.get("current_summary", "")[:240],
        customer_org=_parse_customer_org(sections),
        template_id=_detect_template_id(sections),
        allowed_next_states=allowed_next_states(transition_policy, state_name),
    )


@router.post("/search", response_model=SearchTicketsResponse)
async def search_tickets(
    payload: SearchTicketsRequest,
    plane_client=Depends(get_plane_client),
    transition_policy=Depends(get_transition_policy),
) -> SearchTicketsResponse:
    matched: list[TicketSearchItem] = []
    page = 1
    page_size = max(payload.limit * 2, 25)
    while len(matched) < payload.limit + 1:
        response = await plane_client.list_work_items(page=page, page_size=page_size)
        results = response.get("results", [])
        if not results:
            break
        for ticket in results:
            sections = parse_ticket_sections(ticket.get("description_html", ""))
            if _search_match(ticket, sections, payload):
                matched.append(_search_item(ticket, sections, transition_policy))
        if not response.get("next"):
            break
        page += 1
    matched.sort(key=lambda item: item.updated_at or datetime.min, reverse=True)
    has_more = len(matched) > payload.limit
    return SearchTicketsResponse(items=matched[: payload.limit], applied_filters=payload, has_more=has_more)


@router.post("/create", response_model=CreateTicketResponse)
async def create_ticket(
    payload: CreateTicketRequest,
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
) -> CreateTicketResponse:
    template = registry.get(payload.template_id)
    validate_required_sections(template, payload.content.model_dump())
    normalized_attributes = normalize_attributes(payload.attributes.model_dump())
    context_maps = await _context_maps(plane_client)
    resolved = map_names_to_ids(
        context_maps["state_names_to_ids"],
        context_maps["label_names_to_ids"],
        context_maps["members_by_name"],
        normalized_attributes,
        template,
    )
    title = render_title(template, payload.content.model_dump(), normalized_attributes)
    description_html = render_ticket_html(template, normalized_attributes, payload.content.model_dump(), payload.operator_name)
    ticket_payload = {
        "name": title,
        "description_html": description_html,
        "state_id": resolved["state_id"],
        "label_ids": resolved["label_ids"],
        "assignee_ids": resolved["assignee_ids"],
        "priority": normalized_attributes["priority"],
    }
    ticket = await plane_client.create_work_item(ticket_payload)
    created_note = None
    if payload.options.add_initial_note:
        work_item_id = ticket["id"]
        comment_html = _build_note_html(
            f"[TRIAGE][by:{payload.operator_name}]",
            [
                f"- template: {payload.template_id}",
                f"- initial summary: {payload.content.current_summary}",
                f"- next actions: {payload.content.next_actions_internal}",
            ],
        )
        created_note = await plane_client.create_comment(work_item_id, {"comment_html": comment_html, "access": "INTERNAL"})
    return CreateTicketResponse(identifier=ticket["identifier"], ticket=ticket, created_note=created_note)


@router.get("/{identifier}/context", response_model=TicketContextResponse)
async def get_ticket_context(
    identifier: str,
    notes_limit: int = Query(default=8, ge=1, le=15),
    activities_limit: int = Query(default=8, ge=1, le=15),
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
    transition_policy=Depends(get_transition_policy),
) -> TicketContextResponse:
    ticket = await plane_client.get_work_item_by_identifier(identifier)
    work_item_id = ticket["id"]
    sections = parse_ticket_sections(ticket.get("description_html", ""))
    template_id = _detect_template_id(sections)
    template = registry.get(template_id)
    comments = await plane_client.list_comments(work_item_id, notes_limit)
    activities = await plane_client.list_activities(work_item_id, activities_limit)
    state_name = _state_name(ticket)
    ticket_view = {
        "identifier": ticket["identifier"],
        "title": ticket.get("name", ""),
        "state_name": state_name,
        "priority": ticket.get("priority"),
        "assignee_names": _ticket_assignee_names(ticket),
        "labels": _ticket_label_names(ticket),
        "updated_at": parse_plane_datetime(ticket.get("updated_at")),
        "template_id": template_id,
        "allowed_next_states": allowed_next_states(transition_policy, state_name),
    }
    note_models = [
        InternalNote(
            id=item["id"],
            created_at=parse_plane_datetime(item.get("created_at")),
            actor=item.get("actor_detail", {}).get("display_name") or item.get("actor", {}).get("display_name", ""),
            note_type=parse_note_type(item.get("comment_html", "")),
            body_text=html_to_text(item.get("comment_html", "")),
        )
        for item in comments
        if item.get("access") == "INTERNAL"
    ]
    activity_models = [
        ActivityItem(
            id=item["id"],
            created_at=parse_plane_datetime(item.get("created_at")),
            verb=item.get("verb", ""),
            field=item.get("field", ""),
            old_value=str(item.get("old_value", "")),
            new_value=str(item.get("new_value", "")),
        )
        for item in activities
    ]
    return TicketContextResponse(
        ticket=ticket_view,
        current_summary=sections.get("current_summary", ""),
        sections={key: sections.get(key, "") for key in ["ticket_meta"] + template["required_sections"] + template.get("optional_sections", [])},
        editable_sections=list(template.get("editable_sections", [])),
        recent_internal_notes=note_models,
        recent_activities=activity_models,
        write_guard={"expected_updated_at": ticket.get("updated_at", "")},
    )


@router.post("/{identifier}/upsert-sections", response_model=UpsertSectionsResponse)
async def upsert_sections(
    identifier: str,
    payload: UpsertSectionsRequest,
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
) -> UpsertSectionsResponse:
    ticket = await plane_client.get_work_item_by_identifier(identifier)
    ensure_unmodified(payload.expected_updated_at, parse_plane_datetime(ticket.get("updated_at")))
    sections = parse_ticket_sections(ticket.get("description_html", ""))
    template = registry.get(_detect_template_id(sections))
    ensure_editable_sections(template, payload.sections)
    merged_meta = dict(payload.sections)
    ticket_meta = sections.get("ticket_meta", "")
    if ticket_meta:
        lines = []
        updated_meta = False
        for line in ticket_meta.splitlines():
            if line.startswith("last_updated_by_operator:"):
                lines.append(f"last_updated_by_operator: {payload.operator_name}")
                updated_meta = True
            else:
                lines.append(line)
        if not updated_meta:
            lines.append(f"last_updated_by_operator: {payload.operator_name}")
        merged_meta["ticket_meta"] = "\n".join(lines)
    order = ["ticket_meta"] + template["required_sections"] + template.get("optional_sections", [])
    updated_html = upsert_ticket_sections(ticket.get("description_html", ""), merged_meta, order)
    updated_ticket = await plane_client.update_work_item(identifier, {"description_html": updated_html})
    note_created = False
    if payload.append_note:
        work_item_id = ticket["id"]
        comment_html = _build_note_html(
            f"[SUMMARY_REFRESH][by:{payload.operator_name}]",
            [f"updated sections: {', '.join(payload.sections.keys())}"] + ([f"change summary: {payload.change_summary}"] if payload.change_summary else []),
        )
        await plane_client.create_comment(work_item_id, {"comment_html": comment_html, "access": "INTERNAL"})
        note_created = True
    final_sections = parse_ticket_sections(updated_ticket.get("description_html", updated_html))
    return UpsertSectionsResponse(
        identifier=identifier,
        updated_at=parse_plane_datetime(updated_ticket.get("updated_at")),
        updated_section_keys=list(payload.sections.keys()),
        current_summary=final_sections.get("current_summary", ""),
        note_created=note_created,
    )


@router.post("/{identifier}/transition", response_model=TransitionResponse)
async def transition_ticket(
    identifier: str,
    payload: TransitionRequest,
    plane_client=Depends(get_plane_client),
    transition_policy=Depends(get_transition_policy),
) -> TransitionResponse:
    ticket = await plane_client.get_work_item_by_identifier(identifier)
    ensure_unmodified(payload.expected_updated_at, parse_plane_datetime(ticket.get("updated_at")))
    current_state_name = _state_name(ticket)
    validate_state_transition(transition_policy, current_state_name, payload.to_state_name)
    states = await plane_client.list_states()
    state_ids = {item["name"]: item["id"] for item in states}
    updated_ticket = await plane_client.update_work_item(identifier, {"state_id": state_ids[payload.to_state_name]})
    note_created = False
    if payload.append_note:
        comment_html = _build_note_html(
            f"[STATE_CHANGE][by:{payload.operator_name}]",
            [f"{current_state_name} -> {payload.to_state_name}", f"reason: {payload.reason}"],
        )
        await plane_client.create_comment(ticket["id"], {"comment_html": comment_html, "access": "INTERNAL"})
        note_created = True
    sections = parse_ticket_sections(updated_ticket.get("description_html", ticket.get("description_html", "")))
    return TransitionResponse(
        identifier=identifier,
        from_state_name=current_state_name,
        to_state_name=payload.to_state_name,
        updated_at=parse_plane_datetime(updated_ticket.get("updated_at")),
        allowed_next_states_after=allowed_next_states(transition_policy, payload.to_state_name),
        note_created=note_created,
        current_summary=sections.get("current_summary", ""),
    )


@router.post("/{identifier}/save-email-draft", response_model=SaveEmailDraftResponse)
async def save_email_draft(
    identifier: str,
    payload: SaveEmailDraftRequest,
    plane_client=Depends(get_plane_client),
) -> SaveEmailDraftResponse:
    ticket = await plane_client.get_work_item_by_identifier(identifier)
    ensure_unmodified(payload.expected_updated_at, parse_plane_datetime(ticket.get("updated_at")))
    context_maps = await _context_maps(plane_client)
    label_names = _ticket_label_names(ticket)
    applied_comm_label = None
    if payload.mark_comm_label:
        validate_labels_exist([payload.mark_comm_label], context_maps["label_names_to_ids"])
        label_names = replace_comm_label(label_names, payload.mark_comm_label)
        applied_comm_label = payload.mark_comm_label
        label_ids = [context_maps["label_names_to_ids"][name] for name in label_names]
        ticket = await plane_client.update_work_item(identifier, {"label_ids": label_ids})
    body_html = (
        f"<p><strong>[EMAIL_DRAFT][{escape(payload.draft_type)}][by:{escape(payload.operator_name)}]</strong></p>"
        f"<p><strong>Subject:</strong> {escape(payload.subject)}</p>"
        f"<pre>{escape(payload.body_text)}</pre>"
    )
    comment = await plane_client.create_comment(ticket["id"], {"comment_html": body_html, "access": "INTERNAL"})
    return SaveEmailDraftResponse(
        identifier=identifier,
        updated_at=parse_plane_datetime(ticket.get("updated_at")),
        saved_comment_id=comment["id"],
        applied_comm_label=applied_comm_label,
    )
