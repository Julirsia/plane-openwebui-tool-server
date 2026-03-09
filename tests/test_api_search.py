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


def test_context_returns_rawish_detail_for_legacy_ticket(client) -> None:
    response = client.get("/tickets/SOFT-170/context")
    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]["inferred_template_id"] == "support.troubleshooting"
    assert body["ticket"]["is_legacy_ticket"] is True
    assert body["description_text"] == "고객이 로그인 오류를 제보했습니다.\nSSO 설정 이후부터 발생했다고 합니다."
    assert body["parsed_sections"] == {}
    assert "current_summary" in body["sections"]
