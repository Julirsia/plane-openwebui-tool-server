def test_save_email_draft_creates_internal_comment(client, fake_plane_client) -> None:
    response = client.post(
        "/tickets/SUP-214/save-email-draft",
        json={
            "operator_name": "홍길동",
            "expected_updated_at": "2026-03-09T01:00:00+00:00",
            "draft_type": "progress_update",
            "subject": "[ACME] 로그인 문제 확인 중입니다",
            "body_text": "안녕하세요.\n현재 원인을 확인 중입니다.",
            "mark_comm_label": "comm:draft-ready",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["applied_comm_label"] == "comm:draft-ready"
    payload = fake_plane_client.created_comment_payloads[-1]["payload"]
    assert payload["access"] == "INTERNAL"
    assert "[EMAIL_DRAFT][progress_update][by:홍길동]" in payload["comment_html"]
    assert fake_plane_client.updated_payloads[-1]["work_item_id"] == "wi-214"
    assert "labels" in fake_plane_client.updated_payloads[-1]["payload"]
    assert "label_ids" not in fake_plane_client.updated_payloads[-1]["payload"]


def test_save_email_draft_rejects_unknown_label(client) -> None:
    response = client.post(
        "/tickets/SUP-214/save-email-draft",
        json={
            "operator_name": "홍길동",
            "expected_updated_at": "2026-03-09T01:00:00+00:00",
            "draft_type": "progress_update",
            "subject": "[ACME] 로그인 문제 확인 중입니다",
            "body_text": "안녕하세요.",
            "mark_comm_label": "comm:missing",
        },
    )
    assert response.status_code == 400
