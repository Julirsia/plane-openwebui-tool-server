def test_create_ticket_supports_template_based_payload(client) -> None:
    response = client.post(
        "/tickets/create",
        json={
            "operator_name": "홍길동",
            "template_id": "support.troubleshooting",
            "attributes": {
                "customer_name": "ACME",
                "customer_org": "ACME Corp",
                "channel": "email",
                "product": "auth",
                "severity": "s2",
                "customer_tier": "standard",
                "priority": "high",
                "initial_state_name": "Triage",
                "assignee_name": "김철수",
            },
            "content": {
                "short_summary": "로그인 루프",
                "current_summary": "고객은 로그인 루프를 보고했습니다.",
                "customer_symptom": "대시보드 대신 로그인 페이지로 돌아갑니다.",
                "impact": "관리자 12명 영향",
                "confirmed_facts": "Chrome 과 Edge 공통 발생",
                "open_questions": "비 SSO 고객 영향 미확인",
                "next_actions_internal": "auth 로그 확인",
                "customer_reply_points": "조사 중 안내",
            },
            "options": {"add_initial_note": True},
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["identifier"] == "SUP-999"
    assert body["created_note"] is not None


def test_create_ticket_supports_raw_description_payload(client, fake_plane_client) -> None:
    response = client.post(
        "/tickets/create",
        json={
            "operator_name": "홍길동",
            "title": "원시 텍스트 티켓",
            "description_text": "이 티켓은 외부 시스템에서 가져온 원시 설명입니다.",
            "initial_state_name": "Triage",
            "priority": "medium",
            "label_names": ["kind:billing"],
            "assignee_names": ["홍길동"],
        },
    )
    assert response.status_code == 200
    payload = fake_plane_client.created_tickets[-1]
    assert payload["name"] == "원시 텍스트 티켓"
    assert payload["description_html"] == "<p>이 티켓은 외부 시스템에서 가져온 원시 설명입니다.</p>"
    assert {"state", "labels", "assignees"} <= payload.keys()


def test_create_ticket_rejects_unknown_runtime_label_name(client) -> None:
    response = client.post(
        "/tickets/create",
        json={
            "operator_name": "홍길동",
            "title": "라벨 테스트",
            "description_text": "설명",
            "label_names": ["kind:missing"],
        },
    )
    assert response.status_code == 400
