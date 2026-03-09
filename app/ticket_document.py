from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.parser import html_to_text, parse_ticket_sections

KIND_LABEL_TO_TEMPLATE_ID = {
    "kind:troubleshooting": "support.troubleshooting",
    "kind:howto": "support.howto",
    "kind:billing": "support.billing",
    "kind:feature": "support.feature_request",
}

DEFAULT_TEMPLATE_ID = "support.troubleshooting"
LEGACY_DEFAULTS = {
    "channel": "manual",
    "product": "unknown",
    "severity": "s3",
    "customer_tier": "unknown",
}
LEGACY_OPEN_QUESTIONS = "기존 티켓 형식으로 작성되어 structured sections 가 비어 있습니다."


@dataclass
class TicketDocument:
    template_id: str
    template: dict[str, Any]
    sections: dict[str, str]
    attributes: dict[str, Any]
    is_legacy: bool


def _label_name(raw: dict[str, Any]) -> str:
    return raw.get("name", "")


def _extract_ticket_meta_value(ticket_meta: str, field_name: str) -> str | None:
    lines = [line.strip() for line in ticket_meta.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        if field_name not in line:
            continue
        if ":" in line:
            _, value = line.split(":", 1)
            normalized = value.strip()
            if normalized:
                return normalized
        if idx + 1 < len(lines):
            return lines[idx + 1].lstrip(": ").strip()
    return None


def detect_template_id(sections: dict[str, str]) -> str | None:
    return _extract_ticket_meta_value(sections.get("ticket_meta", ""), "template_id")


def _infer_template_id(ticket: dict[str, Any], registry) -> str:
    label_names = [_label_name(label) for label in ticket.get("labels") or []]
    for label_name in label_names:
        template_id = KIND_LABEL_TO_TEMPLATE_ID.get(label_name)
        if template_id:
            return template_id
    if DEFAULT_TEMPLATE_ID in registry.ids():
        return DEFAULT_TEMPLATE_ID
    return registry.ids()[0]


def _label_value(ticket: dict[str, Any], prefix: str, default: str) -> str:
    for label_name in [_label_name(label) for label in ticket.get("labels") or []]:
        if label_name.startswith(prefix):
            suffix = label_name[len(prefix) :]
            if suffix:
                return suffix
    return default


def _state_name(ticket: dict[str, Any]) -> str:
    state = ticket.get("state")
    if isinstance(state, dict):
        return state.get("name", "")
    return ticket.get("state_name", "")


def _first_assignee_name(ticket: dict[str, Any]) -> str | None:
    for item in ticket.get("assignees") or []:
        display_name = item.get("display_name") or item.get("member", {}).get("display_name")
        if display_name:
            return display_name
    return None


def _legacy_text(ticket: dict[str, Any]) -> str:
    html = ticket.get("description_html", "") or ""
    text = html_to_text(html)
    if text.strip():
        return text.strip()
    return ticket.get("name", "").strip()


def _legacy_attributes(ticket: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_name": "Unknown",
        "customer_org": "Unknown",
        "channel": _label_value(ticket, "channel:", LEGACY_DEFAULTS["channel"]),
        "product": _label_value(ticket, "product:", LEGACY_DEFAULTS["product"]),
        "severity": _label_value(ticket, "severity:", LEGACY_DEFAULTS["severity"]),
        "customer_tier": _label_value(ticket, "customer:", LEGACY_DEFAULTS["customer_tier"]),
        "priority": ticket.get("priority") or template.get("default_priority", "medium"),
        "initial_state_name": _state_name(ticket) or template.get("default_initial_state", "Triage"),
        "assignee_name": _first_assignee_name(ticket),
    }


def _legacy_sections(ticket: dict[str, Any], template: dict[str, Any], template_id: str) -> dict[str, str]:
    raw_text = _legacy_text(ticket)
    attributes = _legacy_attributes(ticket, template)
    customer_context = "\n".join(
        [
            f"고객명: {attributes['customer_name']}",
            f"고객사: {attributes['customer_org']}",
            f"유입 채널: {attributes['channel']}",
            f"고객 등급: {attributes['customer_tier']}",
        ]
    )
    sections: dict[str, str] = {
        "ticket_meta": "\n".join(
            [
                f"template_id: {template_id}",
                f"channel: {attributes['channel']}",
                f"product: {attributes['product']}",
                f"severity: {attributes['severity']}",
                f"customer_tier: {attributes['customer_tier']}",
                "created_by_operator: legacy",
                "last_updated_by_operator: legacy",
                f"customer_name: {attributes['customer_name']}",
                f"customer_org: {attributes['customer_org']}",
            ]
        ),
        "customer_context": customer_context,
        "current_summary": raw_text,
        "customer_symptom": raw_text,
        "impact": "",
        "environment": "",
        "reproduction": "",
        "attempted_actions": "",
        "confirmed_facts": raw_text,
        "open_questions": LEGACY_OPEN_QUESTIONS,
        "suspected_cause": "",
        "next_actions_internal": "",
        "customer_reply_points": "",
        "resolution": "",
    }
    order = ["ticket_meta"] + template["required_sections"] + template.get("optional_sections", [])
    return {key: sections.get(key, "") for key in order}


def resolve_ticket_document(ticket: dict[str, Any], registry) -> TicketDocument:
    parsed_sections = parse_ticket_sections(ticket.get("description_html", ""))
    template_id = detect_template_id(parsed_sections)
    if template_id and template_id in registry.ids():
        template = registry.get(template_id)
        order = ["ticket_meta"] + template["required_sections"] + template.get("optional_sections", [])
        canonical_sections = {key: parsed_sections.get(key, "") for key in order}
        attributes = {
            "customer_name": _extract_ticket_meta_value(canonical_sections.get("ticket_meta", ""), "customer_name") or "Unknown",
            "customer_org": _extract_ticket_meta_value(canonical_sections.get("ticket_meta", ""), "customer_org") or "Unknown",
            "channel": _extract_ticket_meta_value(canonical_sections.get("ticket_meta", ""), "channel") or LEGACY_DEFAULTS["channel"],
            "product": _extract_ticket_meta_value(canonical_sections.get("ticket_meta", ""), "product") or LEGACY_DEFAULTS["product"],
            "severity": _extract_ticket_meta_value(canonical_sections.get("ticket_meta", ""), "severity") or LEGACY_DEFAULTS["severity"],
            "customer_tier": _extract_ticket_meta_value(canonical_sections.get("ticket_meta", ""), "customer_tier") or LEGACY_DEFAULTS["customer_tier"],
            "priority": ticket.get("priority") or template.get("default_priority", "medium"),
            "initial_state_name": _state_name(ticket) or template.get("default_initial_state", "Triage"),
            "assignee_name": _first_assignee_name(ticket),
        }
        return TicketDocument(
            template_id=template_id,
            template=template,
            sections=canonical_sections,
            attributes=attributes,
            is_legacy=False,
        )

    inferred_template_id = _infer_template_id(ticket, registry)
    template = registry.get(inferred_template_id)
    return TicketDocument(
        template_id=inferred_template_id,
        template=template,
        sections=_legacy_sections(ticket, template, inferred_template_id),
        attributes=_legacy_attributes(ticket, template),
        is_legacy=True,
    )
