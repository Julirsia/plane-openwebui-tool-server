def test_update_ticket_supports_raw_patch(client, fake_plane_client) -> None:
    response = client.post(
        "/tickets/SUP-214/update",
        json={
            "operator_name": "홍길동",
            "expected_updated_at": "2026-03-09T01:00:00+00:00",
            "title": "업데이트된 제목",
            "description_text": "원시 텍스트로 설명을 교체합니다.",
            "priority": "urgent",
            "assignee_names": ["홍길동"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["note_created"] is False
    payload = fake_plane_client.updated_payloads[-1]["payload"]
    assert payload["name"] == "업데이트된 제목"
    assert payload["priority"] == "urgent"
    assert payload["description_html"] == "<p>원시 텍스트로 설명을 교체합니다.</p>"
    assert "assignees" in payload


def test_comment_endpoint_adds_internal_comment(client, fake_plane_client) -> None:
    response = client.post(
        "/tickets/SUP-214/comment",
        json={
            "operator_name": "홍길동",
            "body_markdown": "### 확인 내용\n- 로그 확인 중",
        },
    )
    assert response.status_code == 200
    payload = fake_plane_client.created_comment_payloads[-1]["payload"]
    assert payload["access"] == "INTERNAL"
    assert "[COMMENT][by:홍길동]" in payload["comment_html"]


def test_transition_endpoint_updates_state_without_strict_policy_block(client, fake_plane_client) -> None:
    response = client.post(
        "/tickets/SUP-214/transition",
        json={
            "operator_name": "홍길동",
            "expected_updated_at": "2026-03-09T01:00:00+00:00",
            "to_state_name": "Closed",
            "reason": "사내 운영 판단으로 직접 종료",
            "append_note": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["to_state_name"] == "Closed"
    payload = fake_plane_client.updated_payloads[-1]["payload"]
    assert payload["state"] == "state-closed"
