from copy import deepcopy


def test_search_tickets_uses_state_id_filter_when_state_name_is_provided(client, fake_plane_client) -> None:
    response = client.post("/tools/search_tickets", json={"state_name": "Intake", "limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert [item["identifier"] for item in body["items"]] == ["SUP-214"]
    assert fake_plane_client.list_work_items_calls[0] == {
        "limit": 25,
        "offset": 0,
        "expand": "labels,assignees,state,project",
        "state": None,
        "assignee": None,
    }


def test_search_tickets_sorts_by_updated_at_desc_and_has_more(client) -> None:
    response = client.post("/tools/search_tickets", json={"limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["sort"] == "updated_at:desc"
    assert body["has_more"] is True
    assert body["items"][0]["identifier"] == "SUP-215"


def test_search_tickets_filters_by_state_group_even_if_api_filter_is_only_a_hint(client) -> None:
    response = client.post("/tools/search_tickets", json={"state_group": "completed", "limit": 10})

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_search_tickets_deduplicates_repeated_pages(client, fake_plane_client) -> None:
    calls: list[dict[str, int]] = []

    async def repeated_list_work_items(*, limit: int = 50, offset: int = 0, state_id=None, assignee_id=None):
        calls.append({"limit": limit, "offset": offset})
        repeated = [deepcopy(fake_plane_client.work_items["SUP-215"]), deepcopy(fake_plane_client.work_items["SUP-214"])] * 13
        return {"results": repeated[:25]}

    fake_plane_client.list_work_items = repeated_list_work_items

    response = client.post("/tools/search_tickets", json={"limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert [item["identifier"] for item in body["items"]] == ["SUP-215", "SUP-214"]
    assert calls == [{"limit": 25, "offset": 0}, {"limit": 25, "offset": 25}]
