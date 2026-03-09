from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from typing_extensions import Annotated

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


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


class CreateOptions(BaseModel):
    add_initial_note: bool = False


class CreateTicketRequest(BaseModel):
    operator_name: NonEmptyStr
    title: Optional[str] = None
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    initial_state_name: Optional[str] = None
    priority: Optional[str] = None
    label_names: list[str] = Field(default_factory=list)
    assignee_names: list[str] = Field(default_factory=list)
    template_id: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    sections: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] = Field(default_factory=dict)
    options: CreateOptions = Field(default_factory=CreateOptions)
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


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
        if value < 1 or value > 100:
            raise ValueError("limit must be between 1 and 100")
        return value


class TicketSearchItem(BaseModel):
    identifier: str
    title: str
    state_name: str
    priority: Optional[str] = None
    assignee_names: list[str] = Field(default_factory=list)
    label_names: list[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None
    current_summary_excerpt: str = ""
    description_excerpt: str = ""
    inferred_template_id: str = ""
    is_legacy_ticket: bool = False
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
    description_text: str = ""
    description_html: str = ""
    sections: dict[str, str]
    parsed_sections: dict[str, str]
    editable_sections: list[str]
    recent_internal_notes: list[InternalNote]
    recent_activities: list[ActivityItem]
    write_guard: dict[str, str]


class UpdateTicketRequest(BaseModel):
    operator_name: NonEmptyStr
    expected_updated_at: Optional[datetime] = None
    title: Optional[str] = None
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    state_name: Optional[str] = None
    priority: Optional[str] = None
    label_names: Optional[list[str]] = None
    assignee_names: Optional[list[str]] = None
    append_note: bool = False
    note_markdown: Optional[str] = None
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UpdateTicketResponse(BaseModel):
    identifier: str
    updated_at: Optional[datetime] = None
    applied_fields: list[str]
    ticket: dict[str, Any]
    note_created: bool


class TicketCommentRequest(BaseModel):
    operator_name: NonEmptyStr
    body_markdown: NonEmptyStr
    access: Literal["INTERNAL"] = "INTERNAL"


class TicketCommentResponse(BaseModel):
    identifier: str
    comment: dict[str, Any]


class UpsertSectionsRequest(BaseModel):
    operator_name: NonEmptyStr
    expected_updated_at: Optional[datetime] = None
    sections: dict[str, NonEmptyStr]
    append_note: bool = True
    change_summary: Optional[str] = None
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("sections")
    @classmethod
    def validate_sections_non_empty(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("sections must not be empty")
        return value


class UpsertSectionsResponse(BaseModel):
    identifier: str
    updated_at: Optional[datetime] = None
    updated_section_keys: list[str]
    current_summary: str = ""
    note_created: bool


class TransitionRequest(BaseModel):
    operator_name: NonEmptyStr
    expected_updated_at: Optional[datetime] = None
    to_state_name: NonEmptyStr
    reason: Optional[str] = None
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
    expected_updated_at: Optional[datetime] = None
    draft_type: Literal["acknowledge", "request_info", "progress_update", "resolution"]
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    body_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    mark_comm_label: Optional[str] = None


class SaveEmailDraftResponse(BaseModel):
    identifier: str
    updated_at: Optional[datetime] = None
    saved_comment_id: str
    applied_comm_label: Optional[str] = None
