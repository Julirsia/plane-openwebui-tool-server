from pathlib import Path

from app.renderer import render_ticket_html
from app.templates_registry import TemplateRegistry


def test_render_ticket_html_has_required_sections() -> None:
    registry = TemplateRegistry(Path(__file__).resolve().parent.parent / "templates")
    template = registry.get("support.troubleshooting")
    html = render_ticket_html(
        template,
        {
            "customer_name": "ACME",
            "customer_org": "ACME Corp",
            "channel": "email",
            "product": "auth",
            "severity": "s2",
            "customer_tier": "standard",
        },
        {
            "short_summary": "로그인 루프",
            "current_summary": "현재 요약",
            "customer_symptom": "증상",
            "impact": "영향",
            "confirmed_facts": "사실",
            "open_questions": "질문",
            "suspected_cause": "원인",
            "next_actions_internal": "다음 액션",
            "customer_reply_points": "회신 포인트",
        },
        "홍길동",
    )
    assert 'data-ticket-section="ticket_meta"' in html
    for key in template["required_sections"]:
        assert f'data-ticket-section="{key}"' in html
