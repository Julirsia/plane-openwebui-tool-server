from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from app.policy import ensure_editable_sections, normalize_attributes, validate_state_transition
from app.templates_registry import TemplateRegistry


def test_transition_policy_allows_and_denies() -> None:
    policy = yaml.safe_load((Path(__file__).resolve().parent.parent / "policies" / "transition_policy.yaml").read_text())["transitions"]
    validate_state_transition(policy, "Triage", "Resolved")
    with pytest.raises(HTTPException):
        validate_state_transition(policy, "New", "Resolved")


def test_normalize_attributes_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        normalize_attributes(
            {
                "channel": "sms",
                "product": "auth",
                "severity": "s2",
                "customer_tier": "standard",
                "priority": "high",
            }
        )


def test_editable_sections_whitelist_enforced() -> None:
    template = TemplateRegistry(Path(__file__).resolve().parent.parent / "templates").get("support.troubleshooting")
    ensure_editable_sections(template, {"current_summary": "ok"})
    with pytest.raises(HTTPException):
        ensure_editable_sections(template, {"impact": "nope"})
