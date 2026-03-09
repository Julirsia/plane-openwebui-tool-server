def test_create_ticket_resolves_names_but_sends_state_labels_assignees_keys(client, fake_plane_client) -> None:
    response = client.post(
        "/tools/create_ticket",
        json={
            "title": "신규 장애",
            "description_text": "첫 번째 줄\n두 번째 줄",
            "state_name": "resolved",
            "label_names": ["product:billing"],
            "assignee_names": ["홍길동"],
        },
    )

    assert response.status_code == 200
    payload = fake_plane_client.created_tickets[-1]
    assert payload["state"] == "state-resolved"
    assert payload["labels"] == ["label-billing"]
    assert payload["assignees"] == ["member-1"]
    assert "state_id" not in payload
    assert "label_ids" not in payload
    assert "assignee_ids" not in payload


def test_update_ticket_uses_allowlist_patch_and_exact_body_keys(client, fake_plane_client) -> None:
    response = client.post(
        "/tools/update_ticket",
        json={
            "identifier": "SUP-214",
            "expected_updated_at": "2026-03-09T01:00:00+00:00",
            "title": "업데이트된 제목",
            "description_text": "설명 교체",
            "priority": "urgent",
            "label_names": ["product:billing"],
            "assignee_names": ["홍길동"],
        },
    )

    assert response.status_code == 200
    payload = fake_plane_client.updated_payloads[-1]["payload"]
    assert payload == {
        "name": "업데이트된 제목",
        "description_html": "<p>설명 교체</p>",
        "priority": "urgent",
        "labels": ["label-billing"],
        "assignees": ["member-1"],
    }


def test_add_ticket_comment_defaults_to_internal(client, fake_plane_client) -> None:
    response = client.post(
        "/tools/add_ticket_comment",
        json={
            "identifier": "SUP-214",
            "body_markdown": "### 확인 내용\n- 로그 확인 중",
        },
    )

    assert response.status_code == 200
    payload = fake_plane_client.created_comment_payloads[-1]["payload"]
    assert payload["access"] == "INTERNAL"
    assert "<h3>확인 내용</h3>" in payload["comment_html"]


def test_transition_ticket_state_uses_env_state_mapping(client, fake_plane_client) -> None:
    response = client.post(
        "/tools/transition_ticket_state",
        json={
            "identifier": "SUP-214",
            "expected_updated_at": "2026-03-09T01:00:00+00:00",
            "to_state_name": "closed",
        },
    )

    assert response.status_code == 200
    payload = fake_plane_client.updated_payloads[-1]["payload"]
    assert payload == {"state": "state-closed"}
