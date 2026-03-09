from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from fastapi import APIRouter, Depends, Query
from markdown_it import MarkdownIt

from app.config import Settings
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
    TicketCommentRequest,
    TicketCommentResponse,
    TicketContextResponse,
    TicketSearchItem,
    TransitionRequest,
    TransitionResponse,
    UpdateTicketRequest,
    UpdateTicketResponse,
    UpsertSectionsRequest,
    UpsertSectionsResponse,
)
from app.parser import html_to_text, parse_note_type, parse_ticket_sections, upsert_ticket_sections
from app.plane_client import parse_plane_datetime
from app.policy import (
    coerce_note_lines,
    ensure_unmodified,
    key_labels,
    merge_unique_strings,
    pick_allowed_next_states,
    replace_comm_label,
    resolve_label_ids,
    resolve_member_ids,
    resolve_state_id,
    validate_labels_exist,
    validate_state_transition,
)
from app.renderer import render_ticket_html, render_title, text_to_html
from app.ticket_document import resolve_ticket_document

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


def _ticket_description_text(ticket: dict[str, Any], document) -> str:
    description_html = ticket.get("description_html", "") or ""
    raw_text = html_to_text(description_html)
    if raw_text:
        return raw_text
    return document.sections.get("current_summary", "") or ticket.get("name", "")


def _summary_excerpt(ticket: dict[str, Any], document) -> str:
    current_summary = document.sections.get("current_summary", "")
    if current_summary.strip():
        return current_summary[:240]
    return _ticket_description_text(ticket, document)[:240]


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


def _search_match(ticket: dict[str, Any], description_text: str, payload: SearchTicketsRequest) -> bool:
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
                description_text,
            ]
        ).lower()
        if payload.text_query.lower() not in haystack:
            return False
    return True


def _search_item(ticket: dict[str, Any], document, transition_policy: dict[str, list[str]]) -> TicketSearchItem:
    state_name = _state_name(ticket)
    description_excerpt = _ticket_description_text(ticket, document)[:240]
    return TicketSearchItem(
        identifier=ticket["identifier"],
        title=ticket.get("name", ""),
        state_name=state_name,
        priority=ticket.get("priority"),
        assignee_names=_ticket_assignee_names(ticket),
        label_names=_ticket_label_names(ticket),
        updated_at=parse_plane_datetime(ticket.get("updated_at")),
        current_summary_excerpt=_summary_excerpt(ticket, document),
        description_excerpt=description_excerpt,
        inferred_template_id=document.template_id,
        is_legacy_ticket=document.is_legacy,
        allowed_next_states=pick_allowed_next_states(transition_policy, state_name),
    )


def _markdown_to_html(markdown_text: str) -> str:
    return md.render(markdown_text)


def _coerce_description_html(description_html: str | None, description_text: str | None) -> str | None:
    if description_html and description_html.strip():
        return description_html.strip()
    if description_text and description_text.strip():
        return text_to_html(description_text)
    return None


def _coerce_title(payload: CreateTicketRequest) -> str:
    if payload.title and payload.title.strip():
        return payload.title.strip()[:90]
    content = payload.content or {}
    sections = payload.sections or {}
    short_summary = content.get("short_summary") or sections.get("short_summary")
    if short_summary:
        return str(short_summary).strip()[:90]
    description_text = payload.description_text or ""
    if description_text.strip():
        return description_text.strip().splitlines()[0][:90]
    return "New ticket"


def _legacyish_attributes(attributes: dict[str, Any], payload: CreateTicketRequest) -> dict[str, Any]:
    merged = dict(attributes)
    merged.setdefault("customer_name", "Unknown")
    merged.setdefault("customer_org", "Unknown")
    merged.setdefault("channel", "manual")
    merged.setdefault("product", "unknown")
    merged.setdefault("severity", "s3")
    merged.setdefault("customer_tier", "unknown")
    merged.setdefault("priority", payload.priority or merged.get("priority") or "medium")
    merged.setdefault("initial_state_name", payload.initial_state_name or merged.get("initial_state_name") or "Triage")
    return merged


async def _resolve_create_payload(payload: CreateTicketRequest, plane_client, registry) -> tuple[dict[str, Any], str]:
    context_maps = await _context_maps(plane_client)
    title = _coerce_title(payload)
    create_payload: dict[str, Any] = {"name": title}
    attributes = _legacyish_attributes(payload.attributes, payload)
    assignee_names = list(payload.assignee_names)
    if not assignee_names and attributes.get("assignee_name"):
        assignee_names = [str(attributes["assignee_name"])]

    if payload.initial_state_name:
        create_payload["state"] = resolve_state_id(payload.initial_state_name, context_maps["state_names_to_ids"])
    elif attributes.get("initial_state_name"):
        create_payload["state"] = resolve_state_id(str(attributes["initial_state_name"]), context_maps["state_names_to_ids"])
    if payload.priority:
        create_payload["priority"] = payload.priority
    elif attributes.get("priority"):
        create_payload["priority"] = str(attributes["priority"])
    if payload.label_names:
        create_payload["labels"] = resolve_label_ids(payload.label_names, context_maps["label_names_to_ids"])
    if assignee_names:
        create_payload["assignees"] = resolve_member_ids(assignee_names, context_maps["members_by_name"])

    description_html = _coerce_description_html(payload.description_html, payload.description_text)
    if description_html is None and payload.template_id and payload.template_id in registry.ids():
        template = registry.get(payload.template_id)
        sections = dict(payload.sections or {})
        sections.update(payload.content or {})
        description_html = render_ticket_html(template, attributes, sections, payload.operator_name)
        create_payload.setdefault("priority", payload.priority or attributes["priority"] or template.get("default_priority"))
        if "state" not in create_payload and attributes.get("initial_state_name"):
            create_payload["state"] = resolve_state_id(attributes["initial_state_name"], context_maps["state_names_to_ids"])
        label_names = merge_unique_strings(payload.label_names + ([template["default_kind_label"]] if template.get("default_kind_label") else []))
        if label_names:
            create_payload["labels"] = resolve_label_ids(label_names, context_maps["label_names_to_ids"])
    if description_html is not None:
        create_payload["description_html"] = description_html
    return create_payload, description_html or ""


@router.post("/search", response_model=SearchTicketsResponse)
async def search_tickets(
    payload: SearchTicketsRequest,
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
    transition_policy=Depends(get_transition_policy),
) -> SearchTicketsResponse:
    matched: list[TicketSearchItem] = []
    offset = 0
    batch_size = max(payload.limit * 2, 25)
    while len(matched) < payload.limit + 1:
        response = await plane_client.list_work_items(limit=batch_size, offset=offset)
        results = response.get("results", response if isinstance(response, list) else [])
        if not results:
            break
        for ticket in results:
            document = resolve_ticket_document(ticket, registry)
            description_text = _ticket_description_text(ticket, document)
            if _search_match(ticket, description_text, payload):
                matched.append(_search_item(ticket, document, transition_policy))
        if len(results) < batch_size:
            break
        offset += batch_size
    matched.sort(key=lambda item: item.updated_at or datetime.min, reverse=True)
    has_more = len(matched) > payload.limit
    return SearchTicketsResponse(items=matched[: payload.limit], applied_filters=payload, has_more=has_more)


@router.post("/create", response_model=CreateTicketResponse)
async def create_ticket(
    payload: CreateTicketRequest,
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
) -> CreateTicketResponse:
    ticket_payload, description_html = await _resolve_create_payload(payload, plane_client, registry)
    ticket = await plane_client.create_work_item(ticket_payload)
    created_note = None
    if payload.options.add_initial_note:
        summary_line = payload.description_text or html_to_text(description_html)
        comment_html = _build_note_html(
            f"[TRIAGE][by:{payload.operator_name}]",
            [f"title: {ticket_payload['name']}"] + ([f"summary: {summary_line[:300]}"] if summary_line else []),
        )
        created_note = await plane_client.create_comment(ticket["id"], {"comment_html": comment_html, "access": "INTERNAL"})
    return CreateTicketResponse(identifier=ticket["identifier"], ticket=ticket, created_note=created_note)


@router.get("/{identifier}/context", response_model=TicketContextResponse)
async def get_ticket_context(
    identifier: str,
    notes_limit: int = Query(default=8, ge=1, le=20),
    activities_limit: int = Query(default=8, ge=1, le=20),
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
    transition_policy=Depends(get_transition_policy),
) -> TicketContextResponse:
    ticket = await plane_client.get_work_item_by_identifier(identifier)
    document = resolve_ticket_document(ticket, registry)
    description_text = _ticket_description_text(ticket, document)
    comments = await plane_client.list_comments(ticket["id"], notes_limit)
    activities = await plane_client.list_activities(ticket["id"], activities_limit)
    state_name = _state_name(ticket)
    ticket_view = {
        "identifier": ticket["identifier"],
        "id": ticket["id"],
        "title": ticket.get("name", ""),
        "state_name": state_name,
        "priority": ticket.get("priority"),
        "assignee_names": _ticket_assignee_names(ticket),
        "labels": _ticket_label_names(ticket),
        "updated_at": parse_plane_datetime(ticket.get("updated_at")),
        "inferred_template_id": document.template_id,
        "allowed_next_states": pick_allowed_next_states(transition_policy, state_name),
        "is_legacy_ticket": document.is_legacy,
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
    parsed_sections = parse_ticket_sections(ticket.get("description_html", ""))
    return TicketContextResponse(
        ticket=ticket_view,
        current_summary=_summary_excerpt(ticket, document),
        description_text=description_text,
        description_html=ticket.get("description_html", "") or "",
        sections=document.sections,
        parsed_sections=parsed_sections,
        editable_sections=list(document.template.get("editable_sections", [])),
        recent_internal_notes=note_models,
        recent_activities=activity_models,
        write_guard={"expected_updated_at": ticket.get("updated_at", "")},
    )


@router.post("/{identifier}/update", response_model=UpdateTicketResponse)
async def update_ticket(
    identifier: str,
    payload: UpdateTicketRequest,
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
) -> UpdateTicketResponse:
    ticket = await plane_client.get_work_item_by_identifier(identifier)
    ensure_unmodified(payload.expected_updated_at, parse_plane_datetime(ticket.get("updated_at")))
    context_maps = await _context_maps(plane_client)
    patch_payload: dict[str, Any] = {}
    applied_fields: list[str] = []

    if payload.title:
        patch_payload["name"] = payload.title[:90]
        applied_fields.append("name")
    description_html = _coerce_description_html(payload.description_html, payload.description_text)
    if description_html is not None:
        patch_payload["description_html"] = description_html
        applied_fields.append("description_html")
    if payload.state_name:
        patch_payload["state"] = resolve_state_id(payload.state_name, context_maps["state_names_to_ids"])
        applied_fields.append("state")
    if payload.priority is not None:
        patch_payload["priority"] = payload.priority
        applied_fields.append("priority")
    if payload.label_names is not None:
        patch_payload["labels"] = resolve_label_ids(payload.label_names, context_maps["label_names_to_ids"])
        applied_fields.append("labels")
    if payload.assignee_names is not None:
        patch_payload["assignees"] = resolve_member_ids(payload.assignee_names, context_maps["members_by_name"])
        applied_fields.append("assignees")

    updated_ticket = ticket
    if patch_payload:
        updated_ticket = await plane_client.update_work_item(ticket["id"], patch_payload)

    note_created = False
    if payload.append_note and payload.note_markdown:
        note_html = _markdown_to_html(payload.note_markdown)
        comment_html = f"<p><strong>[UPDATE][by:{escape(payload.operator_name)}]</strong></p>{note_html}"
        await plane_client.create_comment(ticket["id"], {"comment_html": comment_html, "access": "INTERNAL"})
        note_created = True

    document = resolve_ticket_document(updated_ticket, registry)
    ticket_view = {
        "identifier": updated_ticket["identifier"],
        "id": updated_ticket["id"],
        "title": updated_ticket.get("name", ""),
        "state_name": _state_name(updated_ticket),
        "priority": updated_ticket.get("priority"),
        "assignee_names": _ticket_assignee_names(updated_ticket),
        "labels": _ticket_label_names(updated_ticket),
        "updated_at": parse_plane_datetime(updated_ticket.get("updated_at")),
        "inferred_template_id": document.template_id,
    }
    return UpdateTicketResponse(
        identifier=identifier,
        updated_at=parse_plane_datetime(updated_ticket.get("updated_at")),
        applied_fields=applied_fields,
        ticket=ticket_view,
        note_created=note_created,
    )


@router.post("/{identifier}/comment", response_model=TicketCommentResponse)
async def add_comment(
    identifier: str,
    payload: TicketCommentRequest,
    plane_client=Depends(get_plane_client),
) -> TicketCommentResponse:
    ticket = await plane_client.get_work_item_by_identifier(identifier)
    comment_body = _markdown_to_html(payload.body_markdown)
    comment_html = f"<p><strong>[COMMENT][by:{escape(payload.operator_name)}]</strong></p>{comment_body}"
    comment = await plane_client.create_comment(ticket["id"], {"comment_html": comment_html, "access": payload.access})
    return TicketCommentResponse(identifier=identifier, comment=comment)


@router.post("/{identifier}/upsert-sections", response_model=UpsertSectionsResponse)
async def upsert_sections(
    identifier: str,
    payload: UpsertSectionsRequest,
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
) -> UpsertSectionsResponse:
    ticket = await plane_client.get_work_item_by_identifier(identifier)
    ensure_unmodified(payload.expected_updated_at, parse_plane_datetime(ticket.get("updated_at")))
    document = resolve_ticket_document(ticket, registry)
    merged_sections = dict(document.sections)
    merged_sections.update(payload.sections)
    order = ["ticket_meta"] + document.template["required_sections"] + document.template.get("optional_sections", [])
    base_html = ticket.get("description_html", "") or ""
    if document.is_legacy or not parse_ticket_sections(base_html):
        base_html = render_ticket_html(document.template, document.attributes, merged_sections, payload.operator_name)
    updated_html = upsert_ticket_sections(base_html, payload.sections, order)
    updated_ticket = await plane_client.update_work_item(ticket["id"], {"description_html": updated_html})
    note_created = False
    if payload.append_note:
        note_lines = [f"updated sections: {', '.join(payload.sections.keys())}"]
        if document.is_legacy:
            note_lines.append("legacy ticket auto-canonicalized")
        if payload.change_summary:
            note_lines.extend(coerce_note_lines(payload.change_summary))
        comment_html = _build_note_html(f"[SECTION_UPDATE][by:{payload.operator_name}]", note_lines)
        await plane_client.create_comment(ticket["id"], {"comment_html": comment_html, "access": "INTERNAL"})
        note_created = True
    updated_document = resolve_ticket_document(updated_ticket, registry)
    return UpsertSectionsResponse(
        identifier=identifier,
        updated_at=parse_plane_datetime(updated_ticket.get("updated_at")),
        updated_section_keys=list(payload.sections.keys()),
        current_summary=_summary_excerpt(updated_ticket, updated_document),
        note_created=note_created,
    )


@router.post("/{identifier}/transition", response_model=TransitionResponse)
async def transition_ticket(
    identifier: str,
    payload: TransitionRequest,
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
    settings: Settings = Depends(get_app_settings),
    transition_policy=Depends(get_transition_policy),
) -> TransitionResponse:
    ticket = await plane_client.get_work_item_by_identifier(identifier)
    ensure_unmodified(payload.expected_updated_at, parse_plane_datetime(ticket.get("updated_at")))
    current_state_name = _state_name(ticket)
    validate_state_transition(
        transition_policy,
        current_state_name,
        payload.to_state_name,
        enforce=settings.enforce_transition_policy,
    )
    states = await plane_client.list_states()
    state_ids = {item["name"]: item["id"] for item in states}
    updated_ticket = await plane_client.update_work_item(ticket["id"], {"state": resolve_state_id(payload.to_state_name, state_ids)})
    note_created = False
    if payload.append_note:
        note_lines = [f"{current_state_name} -> {payload.to_state_name}"] + coerce_note_lines(payload.reason)
        comment_html = _build_note_html(f"[STATE_CHANGE][by:{payload.operator_name}]", note_lines)
        await plane_client.create_comment(ticket["id"], {"comment_html": comment_html, "access": "INTERNAL"})
        note_created = True
    document = resolve_ticket_document(updated_ticket, registry)
    return TransitionResponse(
        identifier=identifier,
        from_state_name=current_state_name,
        to_state_name=payload.to_state_name,
        updated_at=parse_plane_datetime(updated_ticket.get("updated_at")),
        allowed_next_states_after=pick_allowed_next_states(transition_policy, payload.to_state_name),
        note_created=note_created,
        current_summary=_summary_excerpt(updated_ticket, document),
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
        ticket = await plane_client.update_work_item(ticket["id"], {"labels": label_ids})
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
