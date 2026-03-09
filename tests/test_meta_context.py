def test_get_meta_context_returns_runtime_meta_and_state_aliases(client) -> None:
    response = client.get("/tools/get_meta_context")

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["identifier"] == "SUP"
    assert any(item["key"] == "triage" for item in body["states"])
    assert body["state_aliases"]["in_progress"] == ["in progress", "in_progress", "in-progress", "wip"]
    assert any(item["name"] == "product:auth" for item in body["labels"])
    assert any(item["display_name"] == "홍길동" for item in body["members"])
    assert body["defaults"]["comment_access"] == "INTERNAL"
