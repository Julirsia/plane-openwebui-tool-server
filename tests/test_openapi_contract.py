def test_ticket_tool_schemas_require_identifier(client) -> None:
    schemas = client.app.openapi()["components"]["schemas"]

    for schema_name in [
        "GetTicketRequest",
        "TicketCommentsRequest",
        "TicketActivitiesRequest",
        "UpdateTicketRequest",
        "AddTicketCommentRequest",
        "TransitionTicketStateRequest",
    ]:
        assert "identifier" in schemas[schema_name]["required"]


def test_update_ticket_schema_exposes_required_change_fields(client) -> None:
    schema = client.app.openapi()["components"]["schemas"]["UpdateTicketRequest"]

    assert {"required": ["description_text_append"]} in schema["anyOf"]
    assert {"required": ["description_text_replace"]} in schema["anyOf"]
    assert {"required": ["title"]} in schema["anyOf"]


def test_transition_ticket_state_schema_exposes_target_state_fields(client) -> None:
    schema = client.app.openapi()["components"]["schemas"]["TransitionTicketStateRequest"]

    assert {"required": ["to_state_name"]} in schema["anyOf"]
    assert {"required": ["to_state_id"]} in schema["anyOf"]
    assert {"required": ["to_state_group"]} in schema["anyOf"]


def test_add_ticket_comment_rejects_missing_identifier(client) -> None:
    response = client.post(
        "/tools/add_ticket_comment",
        json={
            "body_markdown": "확인했습니다.",
        },
    )

    assert response.status_code == 422
    assert any(item["loc"][-1] == "identifier" for item in response.json()["detail"])


def test_update_ticket_rejects_missing_change_fields(client) -> None:
    response = client.post(
        "/tools/update_ticket",
        json={
            "identifier": "SUP-214",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "value_error"


def test_transition_ticket_state_rejects_missing_target_state(client) -> None:
    response = client.post(
        "/tools/transition_ticket_state",
        json={
            "identifier": "SUP-214",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "value_error"
