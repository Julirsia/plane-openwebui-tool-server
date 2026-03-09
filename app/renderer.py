from __future__ import annotations

from html import escape
from typing import Any

from jinja2 import Template

SECTION_TITLES = {
    "ticket_meta": "티켓 메타",
    "customer_context": "고객 정보",
    "current_summary": "현재 상황 요약",
    "customer_symptom": "고객 증상",
    "impact": "영향도",
    "environment": "환경",
    "reproduction": "재현 정보",
    "attempted_actions": "시도한 조치",
    "confirmed_facts": "확인된 사실",
    "open_questions": "미확인 사항",
    "suspected_cause": "추정 원인",
    "next_actions_internal": "다음 액션",
    "customer_reply_points": "고객 회신 포인트",
    "resolution": "해결 내용",
}


def text_to_html(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return "<p></p>"
    paragraphs = [part.strip() for part in normalized.split("\n\n")]
    html_parts = []
    for paragraph in paragraphs:
        line_html = "<br/>".join(escape(line) for line in paragraph.splitlines())
        html_parts.append(f"<p>{line_html}</p>")
    return "".join(html_parts)


def render_section(key: str, body_html: str) -> str:
    title = SECTION_TITLES.get(key, key.replace("_", " ").title())
    return f'<section data-ticket-section="{escape(key)}"><h2>{escape(title)}</h2>{body_html}</section>'


def render_ticket_meta(template_id: str, attributes: dict[str, Any], operator_name: str) -> str:
    meta = {
        "template_id": template_id,
        "channel": attributes["channel"],
        "product": attributes["product"],
        "severity": attributes["severity"],
        "customer_tier": attributes["customer_tier"],
        "created_by_operator": operator_name,
        "last_updated_by_operator": operator_name,
        "customer_name": attributes["customer_name"],
        "customer_org": attributes["customer_org"],
    }
    items = "".join(f"<li><strong>{escape(key)}</strong>: {escape(str(value))}</li>" for key, value in meta.items())
    return render_section("ticket_meta", f"<ul>{items}</ul>")


def render_ticket_html(
    template: dict[str, Any],
    attributes: dict[str, Any],
    content: dict[str, Any],
    operator_name: str,
) -> str:
    order = ["ticket_meta"] + template["required_sections"] + template.get("optional_sections", [])
    unique_order = list(dict.fromkeys(order))
    pieces = [render_ticket_meta(template["id"], attributes, operator_name)]
    customer_context = "\n".join(
        [
            f"고객명: {attributes['customer_name']}",
            f"고객사: {attributes['customer_org']}",
            f"유입 채널: {attributes['channel']}",
            f"고객 등급: {attributes['customer_tier']}",
        ]
    )
    derived_content = dict(content)
    derived_content.setdefault("customer_context", customer_context)
    for key in unique_order[1:]:
        body = derived_content.get(key, "")
        pieces.append(render_section(key, text_to_html(body)))
    return "".join(pieces)


def render_title(template: dict[str, Any], content: dict[str, str], attributes: dict[str, str]) -> str:
    rendered = Template(template["title_template"]).render(
        short_summary=content["short_summary"],
        product=attributes["product"],
        severity=attributes["severity"],
        customer_org=attributes["customer_org"],
    )
    title = " ".join(rendered.split()).strip()
    return title[:90]
