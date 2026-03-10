from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.deps import get_app_settings, get_plane_client
from app.models import (
    AddTicketCommentRequest,
    AddTicketCommentResponse,
    CreateTicketRequest,
    CreateTicketResponse,
    GetTicketRequest,
    GetTicketResponse,
    LabelItem,
    MemberItem,
    MetaContextResponse,
    SearchTicketsRequest,
    SearchTicketsResponse,
    StateItem,
    TicketActivitiesRequest,
    TicketActivitiesResponse,
    TicketCommentsRequest,
    TicketCommentsResponse,
    TicketSearchItem,
    TransitionTicketStateRequest,
    TransitionTicketStateResponse,
    UpdateTicketRequest,
    UpdateTicketResponse,
)
from app.resolvers import (
    description_excerpt,
    ensure_unmodified,
    html_to_text,
    markdown_to_html,
    member_display_name,
    resolve_assignee_ids,
    resolve_label_ids,
    resolve_state_id,
    resolve_state_ids,
    resolve_ticket_ref,
    search_text,
    state_aliases_for_item,
    state_group_value,
    state_id,
    state_name,
    ticket_identifier,
    text_to_html,
    ticket_assignee_ids,
    ticket_assignee_names,
    ticket_label_ids,
    ticket_label_names,
)

router = APIRouter(prefix="/tools", tags=["tools"])


def _member_email(raw: dict[str, Any]) -> str | None:
    return raw.get("email") or raw.get("member", {}).get("email")


def _state_name_by_id(states: list[dict[str, Any]], target_state_id: str) -> str:
    for item in states:
        if str(item.get("id")) == target_state_id:
            return str(item.get("name", "") or "")
    return ""


def _state_items(states: list[dict[str, Any]]) -> list[StateItem]:
    return [
        StateItem(
            id=str(item["id"]),
            name=str(item["name"]),
            group=state_group_value(item),
            is_default=bool(item.get("default", False)),
            aliases=state_aliases_for_item(item),
        )
        for item in states
    ]


def _search_item(ticket: dict[str, Any]) -> TicketSearchItem:
    return TicketSearchItem(
        id=str(ticket["id"]),
        identifier=ticket_identifier(ticket),
        title=str(ticket.get("name", "")),
        state_name=state_name(ticket),
        state_id=state_id(ticket),
        priority=ticket.get("priority"),
        assignee_names=ticket_assignee_names(ticket),
        label_names=ticket_label_names(ticket),
        updated_at=datetime.fromisoformat(str(ticket["updated_at"]).replace("Z", "+00:00")) if ticket.get("updated_at") else None,
        description_text_excerpt=description_excerpt(ticket),
    )


def _matches_ticket(
    ticket: dict[str, Any],
    *,
    state_ids_filter: set[str],
    assignee_ids_filter: set[str],
    label_ids_filter: set[str],
    updated_after: datetime | None,
    updated_before: datetime | None,
    text_query: str | None,
) -> bool:
    ticket_updated_at = datetime.fromisoformat(str(ticket["updated_at"]).replace("Z", "+00:00")) if ticket.get("updated_at") else None
    if state_ids_filter and state_id(ticket) not in state_ids_filter:
        return False
    if assignee_ids_filter and not assignee_ids_filter.intersection(ticket_assignee_ids(ticket)):
        return False
    if label_ids_filter and not label_ids_filter.issubset(set(ticket_label_ids(ticket))):
        return False
    if updated_after and (ticket_updated_at is None or ticket_updated_at < updated_after):
        return False
    if updated_before and (ticket_updated_at is None or ticket_updated_at > updated_before):
        return False
    if text_query and text_query.lower() not in search_text(ticket):
        return False
    return True


async def _runtime_context(plane_client) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    states = await plane_client.list_states()
    labels = await plane_client.list_labels()
    members = await plane_client.list_project_members()
    return states, labels, members


@router.get("/get_meta_context", response_model=MetaContextResponse)
async def get_meta_context(
    plane_client=Depends(get_plane_client),
    settings: Settings = Depends(get_app_settings),
) -> MetaContextResponse:
    await plane_client.probe_meta_access()
    project = await plane_client.get_project()
    states, labels, members = await _runtime_context(plane_client)
    return MetaContextResponse(
        project=project,
        states=_state_items(states),
        labels=[LabelItem(id=str(item["id"]), name=str(item["name"]), color=item.get("color")) for item in labels],
        members=[
            MemberItem(
                id=str(item["id"]),
                display_name=member_display_name(item),
                email=_member_email(item),
            )
            for item in members
        ],
        defaults={
            "comment_access": settings.default_comment_access,
            "comment_limit": settings.default_comment_limit,
            "activity_limit": settings.default_activity_limit,
        },
        capabilities={
            "ticket_ref_inputs": ["identifier"],
            "ticket_ref_secondary_inputs": ["id"],
            "state_inputs": ["state_id", "state_name", "state_group"],
            "write_fields": [
                "title",
                "description_html",
                "description_text_replace",
                "description_text_append",
                "priority",
                "state",
                "labels",
                "assignees",
            ],
            "reads_are_rawish": True,
        },
    )


@router.post("/search_tickets", response_model=SearchTicketsResponse)
async def search_tickets(
    payload: SearchTicketsRequest,
    plane_client=Depends(get_plane_client),
) -> SearchTicketsResponse:
    states = await plane_client.list_states()
    labels = await plane_client.list_labels() if payload.label_names else []
    members = await plane_client.list_project_members() if payload.assignee_names else []
    resolved_state_ids = resolve_state_ids(
        state_name=payload.state_name,
        state_id_input=payload.state_id,
        state_group_input=payload.state_group,
        runtime_states=states,
    )
    resolved_label_ids = resolve_label_ids(
        label_names=payload.label_names,
        label_ids=payload.label_ids,
        runtime_labels=labels,
    ) or []
    resolved_assignee_ids = resolve_assignee_ids(
        assignee_names=payload.assignee_names,
        assignee_ids=payload.assignee_ids,
        runtime_members=members,
    ) or []

    matched: list[TicketSearchItem] = []
    seen_ticket_ids: set[str] = set()
    seen_page_signatures: set[tuple[str, ...]] = set()
    offset = 0
    batch_size = max(payload.limit * 2, 25)
    while len(matched) < payload.limit + 1:
        response = await plane_client.list_work_items(
            limit=batch_size,
            offset=offset,
            state_id=None,
            assignee_id=None,
        )
        results = response.get("results", response if isinstance(response, list) else [])
        if not results:
            break
        page_signature = tuple(str(ticket.get("id", "")) for ticket in results)
        if page_signature in seen_page_signatures:
            break
        seen_page_signatures.add(page_signature)
        for ticket in results:
            ticket_id_value = str(ticket.get("id", ""))
            if ticket_id_value in seen_ticket_ids:
                continue
            if _matches_ticket(
                ticket,
                state_ids_filter=set(resolved_state_ids),
                assignee_ids_filter=set(resolved_assignee_ids),
                label_ids_filter=set(resolved_label_ids),
                updated_after=payload.updated_after,
                updated_before=payload.updated_before,
                text_query=payload.text_query,
            ):
                matched.append(_search_item(ticket))
                seen_ticket_ids.add(ticket_id_value)
        if len(results) < batch_size:
            break
        offset += batch_size
    matched.sort(key=lambda item: item.updated_at or datetime.min, reverse=True)
    return SearchTicketsResponse(
        items=matched[: payload.limit],
        applied_filters=payload,
        has_more=len(matched) > payload.limit,
    )


@router.post("/get_ticket", response_model=GetTicketResponse)
async def get_ticket(payload: GetTicketRequest, plane_client=Depends(get_plane_client)) -> GetTicketResponse:
    ticket, resolved_ref = await resolve_ticket_ref(
        plane_client=plane_client,
        identifier=payload.identifier,
        work_item_id=payload.id,
    )
    return GetTicketResponse(
        ticket=ticket,
        resolved_ref=resolved_ref,
        description_text=html_to_text(str(ticket.get("description_html", "") or "")),
    )


@router.post("/get_ticket_comments", response_model=TicketCommentsResponse)
async def get_ticket_comments(
    payload: TicketCommentsRequest,
    plane_client=Depends(get_plane_client),
    settings: Settings = Depends(get_app_settings),
) -> TicketCommentsResponse:
    ticket, resolved_ref = await resolve_ticket_ref(
        plane_client=plane_client,
        identifier=payload.identifier,
        work_item_id=payload.id,
    )
    comments = await plane_client.list_comments(ticket["id"], payload.limit or settings.default_comment_limit)
    return TicketCommentsResponse(ticket=resolved_ref, comments=comments)


@router.post("/get_ticket_activities", response_model=TicketActivitiesResponse)
async def get_ticket_activities(
    payload: TicketActivitiesRequest,
    plane_client=Depends(get_plane_client),
    settings: Settings = Depends(get_app_settings),
) -> TicketActivitiesResponse:
    ticket, resolved_ref = await resolve_ticket_ref(
        plane_client=plane_client,
        identifier=payload.identifier,
        work_item_id=payload.id,
    )
    activities = await plane_client.list_activities(ticket["id"], payload.limit or settings.default_activity_limit)
    return TicketActivitiesResponse(ticket=resolved_ref, activities=activities)


@router.post("/create_ticket", response_model=CreateTicketResponse)
async def create_ticket(
    payload: CreateTicketRequest,
    plane_client=Depends(get_plane_client),
) -> CreateTicketResponse:
    states, labels, members = await _runtime_context(plane_client)
    create_payload: dict[str, Any] = {"name": payload.title[:90]}
    description_html = payload.description_html or (text_to_html(payload.description_text) if payload.description_text else None)
    if description_html:
        create_payload["description_html"] = description_html
    if payload.priority is not None:
        create_payload["priority"] = payload.priority
    state_value = resolve_state_id(
        state_name_input=payload.state_name,
        state_id_input=payload.state_id,
        state_group_input=payload.state_group,
        runtime_states=states,
    )
    if state_value:
        create_payload["state"] = state_value
    label_values = resolve_label_ids(label_names=payload.label_names, label_ids=payload.label_ids, runtime_labels=labels)
    if label_values is not None:
        create_payload["labels"] = label_values
    assignee_values = resolve_assignee_ids(
        assignee_names=payload.assignee_names,
        assignee_ids=payload.assignee_ids,
        runtime_members=members,
    )
    if assignee_values is not None:
        create_payload["assignees"] = assignee_values
    ticket = await plane_client.create_work_item(create_payload)
    return CreateTicketResponse(ticket=ticket)


@router.post("/update_ticket", response_model=UpdateTicketResponse)
async def update_ticket(
    payload: UpdateTicketRequest,
    plane_client=Depends(get_plane_client),
) -> UpdateTicketResponse:
    ticket, _ = await resolve_ticket_ref(
        plane_client=plane_client,
        identifier=payload.identifier,
        work_item_id=payload.id,
    )
    ensure_unmodified(payload.expected_updated_at, datetime.fromisoformat(str(ticket["updated_at"]).replace("Z", "+00:00")) if ticket.get("updated_at") else None)
    states, labels, members = await _runtime_context(plane_client)
    patch_payload: dict[str, Any] = {}
    applied_fields: list[str] = []
    if payload.title is not None:
        patch_payload["name"] = payload.title[:90]
        applied_fields.append("title")
    if payload.description_html is not None:
        patch_payload["description_html"] = payload.description_html
        applied_fields.append("description_html")
    elif payload.description_text_replace is not None:
        patch_payload["description_html"] = text_to_html(payload.description_text_replace)
        applied_fields.append("description_text_replace")
    elif payload.description_text_append is not None:
        existing_text = html_to_text(str(ticket.get("description_html", "") or ""))
        combined_text = (
            f"{existing_text}\n\n{payload.description_text_append}".strip()
            if existing_text
            else payload.description_text_append
        )
        patch_payload["description_html"] = text_to_html(combined_text)
        applied_fields.append("description_text_append")
    if payload.priority is not None:
        patch_payload["priority"] = payload.priority
        applied_fields.append("priority")
    state_value = resolve_state_id(
        state_name_input=payload.state_name,
        state_id_input=payload.state_id,
        state_group_input=payload.state_group,
        runtime_states=states,
    )
    if state_value is not None:
        patch_payload["state"] = state_value
        applied_fields.append("state")
    label_values = resolve_label_ids(label_names=payload.label_names, label_ids=payload.label_ids, runtime_labels=labels)
    if label_values is not None:
        patch_payload["labels"] = label_values
        applied_fields.append("labels")
    assignee_values = resolve_assignee_ids(
        assignee_names=payload.assignee_names,
        assignee_ids=payload.assignee_ids,
        runtime_members=members,
    )
    if assignee_values is not None:
        patch_payload["assignees"] = assignee_values
        applied_fields.append("assignees")
    updated_ticket = await plane_client.update_work_item(ticket["id"], patch_payload)
    updated_at = datetime.fromisoformat(str(updated_ticket["updated_at"]).replace("Z", "+00:00")) if updated_ticket.get("updated_at") else None
    return UpdateTicketResponse(ticket=updated_ticket, updated_at=updated_at, applied_fields=applied_fields)


@router.post("/add_ticket_comment", response_model=AddTicketCommentResponse)
async def add_ticket_comment(
    payload: AddTicketCommentRequest,
    plane_client=Depends(get_plane_client),
    settings: Settings = Depends(get_app_settings),
) -> AddTicketCommentResponse:
    ticket, resolved_ref = await resolve_ticket_ref(
        plane_client=plane_client,
        identifier=payload.identifier,
        work_item_id=payload.id,
    )
    access = payload.access or settings.default_comment_access
    comment = await plane_client.create_comment(
        ticket["id"],
        {"comment_html": markdown_to_html(payload.body_markdown), "access": access},
    )
    return AddTicketCommentResponse(ticket=resolved_ref, comment=comment)


@router.post("/transition_ticket_state", response_model=TransitionTicketStateResponse)
async def transition_ticket_state(
    payload: TransitionTicketStateRequest,
    plane_client=Depends(get_plane_client),
) -> TransitionTicketStateResponse:
    ticket, _ = await resolve_ticket_ref(
        plane_client=plane_client,
        identifier=payload.identifier,
        work_item_id=payload.id,
    )
    ensure_unmodified(payload.expected_updated_at, datetime.fromisoformat(str(ticket["updated_at"]).replace("Z", "+00:00")) if ticket.get("updated_at") else None)
    states = await plane_client.list_states()
    target_state_id = resolve_state_id(
        state_name_input=payload.to_state_name,
        state_id_input=payload.to_state_id,
        state_group_input=payload.to_state_group,
        runtime_states=states,
    )
    updated_ticket = await plane_client.update_work_item(ticket["id"], {"state": target_state_id})
    updated_at = datetime.fromisoformat(str(updated_ticket["updated_at"]).replace("Z", "+00:00")) if updated_ticket.get("updated_at") else None
    return TransitionTicketStateResponse(
        ticket=updated_ticket,
        from_state_name=state_name(ticket),
        to_state_name=state_name(updated_ticket) or _state_name_by_id(states, target_state_id),
        updated_at=updated_at,
    )
