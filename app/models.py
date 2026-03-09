from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from typing_extensions import Annotated

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
StateGroup = Literal["backlog", "unstarted", "started", "completed", "cancelled"]


class StateItem(BaseModel):
    id: str
    name: str
    group: Optional[StateGroup] = None
    is_default: bool = False
    aliases: list[str] = Field(default_factory=list)


class MemberItem(BaseModel):
    id: str
    display_name: str
    email: Optional[str] = None


class LabelItem(BaseModel):
    id: str
    name: str
    color: Optional[str] = None


class HealthResponse(BaseModel):
    ok: bool = True


class MetaContextResponse(BaseModel):
    project: dict[str, Any]
    states: list[StateItem]
    labels: list[LabelItem]
    members: list[MemberItem]
    defaults: dict[str, Any]
    capabilities: dict[str, Any]


class TicketRefRequest(BaseModel):
    identifier: Optional[str] = None
    id: Optional[str] = None
    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_ticket_ref(self) -> "TicketRefRequest":
        if not self.identifier and not self.id:
            raise ValueError("Either identifier or id is required")
        return self


class SearchTicketsRequest(BaseModel):
    state_name: Optional[str] = None
    state_id: Optional[str] = None
    state_group: Optional[StateGroup] = None
    assignee_names: list[str] = Field(default_factory=list)
    assignee_ids: list[str] = Field(default_factory=list)
    label_names: list[str] = Field(default_factory=list)
    label_ids: list[str] = Field(default_factory=list)
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
    id: str
    identifier: str
    title: str
    state_name: str
    state_id: str = ""
    priority: Optional[str] = None
    assignee_names: list[str] = Field(default_factory=list)
    label_names: list[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None
    description_text_excerpt: str = ""


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


class GetTicketResponse(BaseModel):
    ticket: dict[str, Any]
    resolved_ref: dict[str, str]
    description_text: str = ""


class GetTicketRequest(TicketRefRequest):
    pass


class TicketCommentsRequest(TicketRefRequest):
    limit: int = 30

    @field_validator("limit")
    @classmethod
    def validate_comment_limit(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("limit must be between 1 and 100")
        return value


class TicketCommentsResponse(BaseModel):
    ticket: dict[str, str]
    comments: list[dict[str, Any]]


class TicketActivitiesRequest(TicketRefRequest):
    limit: int = 30

    @field_validator("limit")
    @classmethod
    def validate_activity_limit(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("limit must be between 1 and 100")
        return value


class TicketActivitiesResponse(BaseModel):
    ticket: dict[str, str]
    activities: list[dict[str, Any]]


class CreateTicketRequest(BaseModel):
    title: NonEmptyStr
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    state_name: Optional[str] = None
    state_id: Optional[str] = None
    state_group: Optional[StateGroup] = None
    priority: Optional[str] = None
    label_names: list[str] = Field(default_factory=list)
    label_ids: list[str] = Field(default_factory=list)
    assignee_names: list[str] = Field(default_factory=list)
    assignee_ids: list[str] = Field(default_factory=list)
    model_config = ConfigDict(str_strip_whitespace=True)


class CreateTicketResponse(BaseModel):
    ticket: dict[str, Any]


class UpdateTicketRequest(TicketRefRequest):
    expected_updated_at: Optional[datetime] = None
    title: Optional[str] = None
    description_html: Optional[str] = None
    description_text_replace: Optional[str] = None
    description_text_append: Optional[str] = None
    state_name: Optional[str] = None
    state_id: Optional[str] = None
    state_group: Optional[StateGroup] = None
    priority: Optional[str] = None
    label_names: Optional[list[str]] = None
    label_ids: Optional[list[str]] = None
    assignee_names: Optional[list[str]] = None
    assignee_ids: Optional[list[str]] = None
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UpdateTicketResponse(BaseModel):
    ticket: dict[str, Any]
    updated_at: Optional[datetime] = None
    applied_fields: list[str]


class AddTicketCommentRequest(TicketRefRequest):
    body_markdown: NonEmptyStr
    access: Literal["INTERNAL", "EXTERNAL"] = "INTERNAL"


class AddTicketCommentResponse(BaseModel):
    ticket: dict[str, str]
    comment: dict[str, Any]


class TransitionTicketStateRequest(TicketRefRequest):
    expected_updated_at: Optional[datetime] = None
    to_state_name: Optional[str] = None
    to_state_id: Optional[str] = None
    to_state_group: Optional[StateGroup] = None

    @model_validator(mode="after")
    def validate_target_state(self) -> "TransitionTicketStateRequest":
        if not self.to_state_name and not self.to_state_id and not self.to_state_group:
            raise ValueError("Either to_state_name, to_state_id, or to_state_group is required")
        return self


class TransitionTicketStateResponse(BaseModel):
    ticket: dict[str, Any]
    from_state_name: str
    to_state_name: str
    updated_at: Optional[datetime] = None
