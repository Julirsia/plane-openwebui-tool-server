def test_get_meta_context_returns_runtime_meta_and_state_descriptors(client) -> None:
    response = client.get("/tools/get_meta_context")

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["identifier"] == "SUP"
    assert any(item["name"] == "Intake" and item["group"] == "backlog" and item["is_default"] is True for item in body["states"])
    assert any("waiting_qa" in item["aliases"] for item in body["states"] if item["name"] == "Waiting QA")
    assert any(item["name"] == "product:auth" for item in body["labels"])
    assert any(item["display_name"] == "홍길동" for item in body["members"])
    assert body["defaults"]["comment_access"] == "INTERNAL"
