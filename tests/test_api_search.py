def test_search_sorts_by_updated_at_desc_and_has_more(client) -> None:
    response = client.post("/tickets/search", json={"state_names": [], "limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["sort"] == "updated_at:desc"
    assert body["has_more"] is True
    assert body["items"][0]["identifier"] == "SUP-215"


def test_context_exposes_editable_sections(client) -> None:
    response = client.get("/tickets/SUP-214/context")
    assert response.status_code == 200
    body = response.json()
    assert "current_summary" in body["editable_sections"]
    assert body["write_guard"]["expected_updated_at"] == "2026-03-09T01:00:00+00:00"
