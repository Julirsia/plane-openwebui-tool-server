def test_search_sorts_by_updated_at_desc_and_has_more(client) -> None:
    response = client.post("/tickets/search", json={"state_names": [], "limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["sort"] == "updated_at:desc"
    assert body["has_more"] is True
    assert body["items"][0]["identifier"] == "SUP-215"


def test_search_uses_limit_offset_and_expand(client, fake_plane_client) -> None:
    response = client.post("/tickets/search", json={"state_names": [], "limit": 1})
    assert response.status_code == 200
    assert fake_plane_client.list_work_items_calls[0] == {
        "limit": 25,
        "offset": 0,
        "expand": "labels,assignees,state",
    }


def test_context_exposes_editable_sections(client) -> None:
    response = client.get("/tickets/SUP-214/context")
    assert response.status_code == 200
    body = response.json()
    assert "current_summary" in body["editable_sections"]
    assert body["write_guard"]["expected_updated_at"] == "2026-03-09T01:00:00+00:00"
    assert client is not None


def test_context_supports_legacy_ticket_without_ticket_meta(client) -> None:
    response = client.get("/tickets/SOFT-170/context")
    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]["template_id"] == "support.troubleshooting"
    assert body["ticket"]["is_legacy_ticket"] is True
    assert body["current_summary"] == "고객이 로그인 오류를 제보했습니다.\nSSO 설정 이후부터 발생했다고 합니다."
    assert "current_summary" in body["editable_sections"]
