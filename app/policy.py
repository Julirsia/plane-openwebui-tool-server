from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, status

KEY_LABEL_PREFIXES = ("channel:", "kind:", "product:", "severity:", "customer:", "comm:")


def load_transition_policy(path: str) -> dict[str, list[str]]:
    policy_path = Path(path)
    if not policy_path.exists():
        return {}
    data = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    return data.get("transitions", {})


def validate_state_transition(
    policy: dict[str, list[str]],
    current_state_name: str,
    next_state_name: str,
    *,
    enforce: bool = False,
) -> None:
    if not enforce:
        return
    allowed = policy.get(current_state_name)
    if not allowed:
        return
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


def ensure_unmodified(expected_updated_at: datetime | None, actual_updated_at: datetime | None) -> None:
    if expected_updated_at is None or actual_updated_at is None:
        return
    if expected_updated_at != actual_updated_at:
        raise HTTPException(status_code=409, detail="Ticket was modified after the provided context")


def key_labels(labels: list[str]) -> list[str]:
    return [label for label in labels if label.startswith(KEY_LABEL_PREFIXES)]


def replace_comm_label(label_names: list[str], new_comm_label: str) -> list[str]:
    kept = [label for label in label_names if not label.startswith("comm:")]
    kept.append(new_comm_label)
    return kept


def resolve_state_id(state_name: str, state_names_to_ids: dict[str, str]) -> str:
    resolved = state_names_to_ids.get(state_name)
    if resolved is None:
        raise HTTPException(status_code=400, detail=f"Unknown state name: {state_name}")
    return resolved


def resolve_label_ids(label_names: list[str], label_names_to_ids: dict[str, str]) -> list[str]:
    validate_labels_exist(label_names, label_names_to_ids)
    return [label_names_to_ids[name] for name in label_names]


def resolve_member_ids(member_names: list[str], members_by_name: dict[str, str]) -> list[str]:
    member_ids: list[str] = []
    missing: list[str] = []
    for member_name in member_names:
        member_id = members_by_name.get(member_name)
        if member_id is None:
            missing.append(member_name)
            continue
        member_ids.append(member_id)
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown assignee name(s): {', '.join(sorted(missing))}")
    return member_ids


def pick_allowed_next_states(policy: dict[str, list[str]], current_state_name: str) -> list[str]:
    return list(policy.get(current_state_name, []))


def coerce_note_lines(reason: str | None) -> list[str]:
    if not reason:
        return []
    return [line.strip() for line in reason.splitlines() if line.strip()]


def merge_unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
