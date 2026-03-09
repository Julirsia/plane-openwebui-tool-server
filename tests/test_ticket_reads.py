def test_get_ticket_supports_identifier_lookup(client, fake_plane_client) -> None:
    response = client.post("/tools/get_ticket", json={"identifier": "SUP-214"})

    assert response.status_code == 200
    body = response.json()
    assert body["resolved_ref"]["ref_type"] == "identifier"
    assert body["ticket"]["id"] == "wi-214"
    assert "로그인 루프" in body["description_text"]
    assert fake_plane_client.identifier_lookup_calls == ["SUP-214"]


def test_get_ticket_supports_uuid_lookup(client, fake_plane_client) -> None:
    response = client.post("/tools/get_ticket", json={"id": "wi-170"})

    assert response.status_code == 200
    body = response.json()
    assert body["resolved_ref"]["ref_type"] == "id"
    assert body["ticket"]["identifier"] == "SOFT-170"
    assert fake_plane_client.id_lookup_calls == ["wi-170"]


def test_get_ticket_comments_and_activities_use_project_scoped_uuid(client) -> None:
    comments_response = client.post("/tools/get_ticket_comments", json={"identifier": "SUP-214", "limit": 5})
    activities_response = client.post("/tools/get_ticket_activities", json={"identifier": "SUP-214", "limit": 5})

    assert comments_response.status_code == 200
    assert activities_response.status_code == 200
    assert comments_response.json()["comments"][0]["access"] == "INTERNAL"
    assert activities_response.json()["activities"][0]["field"] == "state"
