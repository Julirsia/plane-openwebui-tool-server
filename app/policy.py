from __future__ import annotations

from datetime import datetime
from typing import Any

import yaml
from fastapi import HTTPException, status

from app.models import (
    VALID_CHANNELS,
    VALID_CUSTOMER_TIERS,
    VALID_PRIORITIES,
    VALID_PRODUCTS,
    VALID_SEVERITIES,
    validate_enum,
)

SECTION_LENGTH_LIMITS = {
    "current_summary": 800,
    "customer_reply_points": 1200,
}
DEFAULT_SECTION_LENGTH_LIMIT = 2000
KEY_LABEL_PREFIXES = ("channel:", "kind:", "product:", "severity:", "customer:", "comm:")


def load_transition_policy(path: str) -> dict[str, list[str]]:
    data = yaml.safe_load(open(path, "r", encoding="utf-8"))
    return data["transitions"]


def validate_state_transition(policy: dict[str, list[str]], current_state_name: str, next_state_name: str) -> None:
    allowed = policy.get(current_state_name, [])
    if next_state_name not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transition not allowed: {current_state_name} -> {next_state_name}",
        )


def validate_labels_exist(label_names: list[str], label_names_to_ids: dict[str, str]) -> None:
    missing = [label for label in label_names if label not in label_names_to_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown label name(s): {', '.join(sorted(missing))}",
        )


def validate_required_sections(template: dict[str, Any], content: dict[str, str]) -> None:
    missing = [
        section
        for section in template["required_sections"]
        if section != "customer_context" and not content.get(section, "").strip()
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required content section(s): {', '.join(missing)}",
        )


def normalize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(attributes)
    normalized["channel"] = validate_enum("channel", normalized["channel"], VALID_CHANNELS)
    normalized["product"] = validate_enum("product", normalized["product"], VALID_PRODUCTS)
    normalized["severity"] = validate_enum("severity", normalized["severity"], VALID_SEVERITIES)
    normalized["customer_tier"] = validate_enum("customer_tier", normalized["customer_tier"], VALID_CUSTOMER_TIERS)
    normalized["priority"] = validate_enum("priority", normalized["priority"], VALID_PRIORITIES)
    return normalized


def map_names_to_ids(
    state_names_to_ids: dict[str, str],
    label_names_to_ids: dict[str, str],
    members_by_name: dict[str, str],
    attributes: dict[str, Any],
    template: dict[str, Any],
    comm_label: str | None = None,
) -> dict[str, Any]:
    if attributes["initial_state_name"] not in state_names_to_ids:
        raise HTTPException(status_code=400, detail=f"Unknown state name: {attributes['initial_state_name']}")
    label_names = [
        f"channel:{attributes['channel']}",
        template["default_kind_label"],
        f"product:{attributes['product']}",
        f"severity:{attributes['severity']}",
        f"customer:{attributes['customer_tier']}",
    ]
    if comm_label:
        label_names.append(comm_label)
    validate_labels_exist(label_names, label_names_to_ids)
    assignee_ids: list[str] = []
    assignee_name = attributes.get("assignee_name")
    if assignee_name:
        assignee_id = members_by_name.get(assignee_name)
        if assignee_id is None:
            raise HTTPException(status_code=400, detail=f"Unknown assignee_name: {assignee_name}")
        assignee_ids.append(assignee_id)
    return {
        "state_id": state_names_to_ids[attributes["initial_state_name"]],
        "label_ids": [label_names_to_ids[name] for name in label_names],
        "label_names": label_names,
        "assignee_ids": assignee_ids,
    }


def allowed_next_states(policy: dict[str, list[str]], current_state_name: str) -> list[str]:
    return list(policy.get(current_state_name, []))


def ensure_editable_sections(template: dict[str, Any], sections: dict[str, str]) -> None:
    allowed = set(template.get("editable_sections", []))
    unknown = sorted(set(sections) - allowed)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown or non-editable section(s): {', '.join(unknown)}")
    for key, value in sections.items():
        limit = SECTION_LENGTH_LIMITS.get(key, DEFAULT_SECTION_LENGTH_LIMIT)
        if len(value.strip()) > limit:
            raise HTTPException(status_code=400, detail=f"Section '{key}' exceeds max length {limit}")


def ensure_unmodified(expected_updated_at: datetime, actual_updated_at: datetime | None) -> None:
    if actual_updated_at is None:
        return
    if expected_updated_at != actual_updated_at:
        raise HTTPException(status_code=409, detail="Ticket was modified after the provided context")


def key_labels(labels: list[str]) -> list[str]:
    return [label for label in labels if label.startswith(KEY_LABEL_PREFIXES)]


def replace_comm_label(label_names: list[str], new_comm_label: str) -> list[str]:
    kept = [label for label in label_names if not label.startswith("comm:")]
    kept.append(new_comm_label)
    return kept
