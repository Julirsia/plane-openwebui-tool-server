def test_upsert_sections_updates_allowed_fields_and_adds_note(client, fake_plane_client) -> None:
    response = client.post(
        "/tickets/SUP-214/upsert-sections",
        json={
            "operator_name": "홍길동",
            "expected_updated_at": "2026-03-09T01:00:00+00:00",
            "sections": {
                "current_summary": "현재까지 확인된 바로는 SSO 고객에만 영향이 있습니다.",
                "confirmed_facts": "SSO 고객에서만 재현됩니다.",
            },
            "append_note": True,
            "change_summary": "summary refresh",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated_section_keys"] == ["current_summary", "confirmed_facts"]
    assert body["note_created"] is True
    assert fake_plane_client.created_comment_payloads[-1]["payload"]["access"] == "INTERNAL"
    assert fake_plane_client.updated_payloads[-1]["work_item_id"] == "wi-214"
    assert "description_html" in fake_plane_client.updated_payloads[-1]["payload"]


def test_upsert_sections_rejects_unknown_section(client) -> None:
    response = client.post(
        "/tickets/SUP-214/upsert-sections",
        json={
            "operator_name": "홍길동",
            "expected_updated_at": "2026-03-09T01:00:00+00:00",
            "sections": {"impact": "바꾸면 안 됨"},
            "append_note": False,
        },
    )
    assert response.status_code == 400


def test_upsert_sections_auto_canonicalizes_legacy_ticket(client, fake_plane_client) -> None:
    response = client.post(
        "/tickets/SOFT-170/upsert-sections",
        json={
            "operator_name": "홍길동",
            "expected_updated_at": "2026-03-08T01:00:00+00:00",
            "sections": {"current_summary": "legacy 티켓을 canonical 형식으로 승격했습니다."},
            "append_note": True,
        },
    )
    assert response.status_code == 200
    payload = fake_plane_client.updated_payloads[-1]["payload"]
    assert 'data-ticket-section="ticket_meta"' in payload["description_html"]
    assert "legacy 티켓을 canonical 형식으로 승격했습니다." in payload["description_html"]
    assert "legacy ticket auto-canonicalized" in fake_plane_client.created_comment_payloads[-1]["payload"]["comment_html"]
