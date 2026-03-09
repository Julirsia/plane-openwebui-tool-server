import pytest
from fastapi import HTTPException

from app.policy import resolve_label_ids, resolve_member_ids, resolve_state_id, validate_state_transition


def test_transition_policy_is_optional_by_default() -> None:
    validate_state_transition({"New": ["Triage"]}, "New", "Closed", enforce=False)
    with pytest.raises(HTTPException):
        validate_state_transition({"New": ["Triage"]}, "New", "Closed", enforce=True)


def test_runtime_name_resolution_helpers() -> None:
    assert resolve_state_id("Triage", {"Triage": "state-triage"}) == "state-triage"
    assert resolve_label_ids(["kind:billing"], {"kind:billing": "label-kind:billing"}) == ["label-kind:billing"]
    assert resolve_member_ids(["홍길동"], {"홍길동": "member-1"}) == ["member-1"]
