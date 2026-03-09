def test_create_ticket_valid_payload(client) -> None:
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
                "environment": "Windows 11 / Chrome",
                "reproduction": "재현됨",
                "attempted_actions": "쿠키 삭제",
                "confirmed_facts": "Chrome 과 Edge 공통 발생",
                "open_questions": "비 SSO 고객 영향 미확인",
                "suspected_cause": "redirect 문제 가능성",
                "next_actions_internal": "auth 로그 확인",
                "customer_reply_points": "조사 중 안내",
                "resolution": "",
            },
            "options": {"add_initial_note": True},
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["identifier"] == "SUP-999"
    assert body["created_note"] is not None


def test_create_ticket_invalid_label_returns_400(client) -> None:
    response = client.post(
        "/tickets/create",
        json={
            "operator_name": "홍길동",
            "template_id": "support.troubleshooting",
            "attributes": {
                "customer_name": "ACME",
                "customer_org": "ACME Corp",
                "channel": "email",
                "product": "missing",
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
                "environment": "",
                "reproduction": "",
                "attempted_actions": "",
                "confirmed_facts": "Chrome 과 Edge 공통 발생",
                "open_questions": "비 SSO 고객 영향 미확인",
                "suspected_cause": "",
                "next_actions_internal": "auth 로그 확인",
                "customer_reply_points": "조사 중 안내",
                "resolution": "",
            },
        },
    )
    assert response.status_code == 400


def test_create_ticket_missing_required_section_returns_400(client) -> None:
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
            },
            "content": {
                "short_summary": "로그인 루프",
                "current_summary": "",
                "customer_symptom": "대시보드 대신 로그인 페이지로 돌아갑니다.",
                "impact": "관리자 12명 영향",
                "environment": "",
                "reproduction": "",
                "attempted_actions": "",
                "confirmed_facts": "Chrome 과 Edge 공통 발생",
                "open_questions": "비 SSO 고객 영향 미확인",
                "suspected_cause": "",
                "next_actions_internal": "auth 로그 확인",
                "customer_reply_points": "조사 중 안내",
                "resolution": "",
            },
        },
    )
    assert response.status_code == 422
