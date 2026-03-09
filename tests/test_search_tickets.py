def test_search_tickets_uses_state_id_filter_when_state_name_is_provided(client, fake_plane_client) -> None:
    response = client.post("/tools/search_tickets", json={"state_names": ["triage"], "limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert [item["identifier"] for item in body["items"]] == ["SUP-214"]
    assert fake_plane_client.list_work_items_calls[0] == {
        "limit": 25,
        "offset": 0,
        "expand": "labels,assignees,state",
        "state": "state-triage",
        "assignee": None,
    }


def test_search_tickets_sorts_by_updated_at_desc_and_has_more(client) -> None:
    response = client.post("/tools/search_tickets", json={"limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["sort"] == "updated_at:desc"
    assert body["has_more"] is True
    assert body["items"][0]["identifier"] == "SUP-215"
