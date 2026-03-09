from app.parser import parse_ticket_sections, upsert_ticket_sections


def test_parse_ticket_sections_extracts_plain_text() -> None:
    html = (
        '<section data-ticket-section="current_summary"><h2>현재 상황 요약</h2><p>line 1<br/>line 2</p></section>'
        '<section data-ticket-section="confirmed_facts"><h2>확인된 사실</h2><p>fact</p></section>'
    )
    sections = parse_ticket_sections(html)
    assert sections["current_summary"] == "line 1\nline 2"
    assert sections["confirmed_facts"] == "fact"
    assert sections.get("open_questions") is None


def test_upsert_ticket_sections_replaces_and_appends_in_order() -> None:
    html = (
        '<section data-ticket-section="ticket_meta"><h2>meta</h2><p>a</p></section>'
        '<section data-ticket-section="current_summary"><h2>summary</h2><p>old</p></section>'
        '<section data-ticket-section="customer_reply_points"><h2>reply</h2><p>keep</p></section>'
    )
    updated = upsert_ticket_sections(
        html,
        {"current_summary": "new", "confirmed_facts": "fact"},
        ["ticket_meta", "current_summary", "confirmed_facts", "customer_reply_points"],
    )
    sections = parse_ticket_sections(updated)
    assert sections["current_summary"] == "new"
    assert sections["confirmed_facts"] == "fact"
    assert updated.index('data-ticket-section="confirmed_facts"') < updated.index('data-ticket-section="customer_reply_points"')
