from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from typing_extensions import Annotated

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

VALID_CHANNELS = {"email", "chat", "phone", "manual"}
VALID_PRODUCTS = {"auth", "api", "admin", "billing", "unknown"}
VALID_SEVERITIES = {"s1", "s2", "s3", "s4"}
VALID_CUSTOMER_TIERS = {"premium", "standard", "unknown"}
VALID_PRIORITIES = {"none", "urgent", "high", "medium", "low"}
VALID_EMAIL_DRAFT_TYPES = {"acknowledge", "request_info", "progress_update", "resolution"}


class MetaItem(BaseModel):
    id: str
    name: str


class MemberItem(BaseModel):
    id: str
    display_name: str


class TemplateInfo(BaseModel):
    id: str
    display_name: str
    editable_sections: list[str]


class HealthResponse(BaseModel):
    ok: bool = True


class ContextResponse(BaseModel):
    project: dict[str, Any]
    states: list[MetaItem]
    labels: list[MetaItem]
    members: list[MemberItem]
    templates: list[TemplateInfo]
    transition_policy: dict[str, list[str]]
    editable_sections_by_template: dict[str, list[str]]
    limits: dict[str, int]


class TicketAttributes(BaseModel):
    customer_name: NonEmptyStr
    customer_org: NonEmptyStr
    channel: NonEmptyStr
    product: NonEmptyStr
    severity: NonEmptyStr
    customer_tier: NonEmptyStr
    priority: NonEmptyStr
    initial_state_name: NonEmptyStr
    assignee_name: Optional[str] = None


class TicketContent(BaseModel):
    short_summary: NonEmptyStr
    current_summary: NonEmptyStr
    customer_symptom: NonEmptyStr
    impact: NonEmptyStr
    environment: str = ""
    reproduction: str = ""
    attempted_actions: str = ""
    confirmed_facts: NonEmptyStr
    open_questions: NonEmptyStr
    suspected_cause: str = ""
    next_actions_internal: NonEmptyStr
    customer_reply_points: NonEmptyStr
    resolution: str = ""


class CreateOptions(BaseModel):
    add_initial_note: bool = False


class CreateTicketRequest(BaseModel):
    operator_name: NonEmptyStr
    template_id: NonEmptyStr
    attributes: TicketAttributes
    content: TicketContent
    options: CreateOptions = Field(default_factory=CreateOptions)


class CreateTicketResponse(BaseModel):
    identifier: str
    ticket: dict[str, Any]
    created_note: Optional[dict[str, Any]] = None


class SearchTicketsRequest(BaseModel):
    state_names: list[str] = Field(default_factory=list)
    assignee_name: Optional[str] = None
    label_names: list[str] = Field(default_factory=list)
    updated_after: Optional[datetime] = None
    updated_before: Optional[datetime] = None
    text_query: Optional[str] = None
    limit: int = 20

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if value < 1 or value > 50:
            raise ValueError("limit must be between 1 and 50")
        return value


class TicketSearchItem(BaseModel):
    identifier: str
    title: str
    state_name: str
    priority: Optional[str] = None
    assignee_names: list[str] = Field(default_factory=list)
    key_labels: list[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None
    current_summary_excerpt: str = ""
    customer_org: str = ""
    template_id: str = ""
    allowed_next_states: list[str] = Field(default_factory=list)


class SearchTicketsResponse(BaseModel):
    items: list[TicketSearchItem]
    applied_filters: SearchTicketsRequest
    has_more: bool
    sort: str = "updated_at:desc"


class InternalNote(BaseModel):
    id: str
    created_at: Optional[datetime] = None
    actor: str = ""
    note_type: str = "internal_note"
    body_text: str = ""


class ActivityItem(BaseModel):
    id: str
    created_at: Optional[datetime] = None
    verb: str = ""
    field: str = ""
    old_value: str = ""
    new_value: str = ""


class TicketContextResponse(BaseModel):
    ticket: dict[str, Any]
    current_summary: str = ""
    sections: dict[str, str]
    editable_sections: list[str]
    recent_internal_notes: list[InternalNote]
    recent_activities: list[ActivityItem]
    write_guard: dict[str, str]


class UpsertSectionsRequest(BaseModel):
    operator_name: NonEmptyStr
    expected_updated_at: datetime
    sections: dict[str, NonEmptyStr]
    append_note: bool = True
    change_summary: Annotated[Optional[str], StringConstraints(max_length=200)] = None
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("sections")
    @classmethod
    def validate_sections_count(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("sections must not be empty")
        if len(value) > 6:
            raise ValueError("up to 6 sections can be updated at once")
        return value


class UpsertSectionsResponse(BaseModel):
    identifier: str
    updated_at: Optional[datetime] = None
    updated_section_keys: list[str]
    current_summary: str = ""
    note_created: bool


class TransitionRequest(BaseModel):
    operator_name: NonEmptyStr
    expected_updated_at: datetime
    to_state_name: NonEmptyStr
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    append_note: bool = True


class TransitionResponse(BaseModel):
    identifier: str
    from_state_name: str
    to_state_name: str
    updated_at: Optional[datetime] = None
    allowed_next_states_after: list[str]
    note_created: bool
    current_summary: str = ""


class SaveEmailDraftRequest(BaseModel):
    operator_name: NonEmptyStr
    expected_updated_at: datetime
    draft_type: Literal["acknowledge", "request_info", "progress_update", "resolution"]
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    body_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    mark_comm_label: Optional[str] = None


class SaveEmailDraftResponse(BaseModel):
    identifier: str
    updated_at: Optional[datetime] = None
    saved_comment_id: str
    applied_comm_label: Optional[str] = None


def validate_enum(name: str, value: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed))}")
    return value
