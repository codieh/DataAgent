from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class AgentProfile(ApiModel):
    id: str
    name: str
    description: str
    is_default: bool = False


class DatasourceSummary(ApiModel):
    id: str
    name: str
    type: str
    status: str
    is_default: bool = False


class BootstrapResponse(ApiModel):
    default_agent_id: str
    agents: list[AgentProfile]
    recommended_questions: list[str]
    datasources: list[DatasourceSummary]
    features: dict[str, bool]


class HealthResponse(ApiModel):
    status: str
    database: str
    version: str
    timestamp: datetime


class ConversationCreate(ApiModel):
    title: str | None = Field(default=None, max_length=200)
    agent_id: str = "default-analysis"
    datasource_id: str = "sales-db"


class ConversationUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    agent_id: str | None = None
    datasource_id: str | None = None


class MessageResponse(ApiModel):
    id: str
    conversation_id: str
    run_id: str | None
    role: str
    content: str
    content_type: str
    created_at: datetime


class ConversationSummary(ApiModel):
    id: str
    title: str
    agent_id: str
    datasource_id: str
    status: str
    last_run_id: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    summary: str | None
    messages: list[MessageResponse]
    runs: list["RunSummary"]


class ConversationListResponse(ApiModel):
    items: list[ConversationSummary]
    next_cursor: str | None = None


class RunCreate(ApiModel):
    query: str = Field(min_length=1, max_length=20_000)
    agent_id: str | None = None
    datasource_id: str | None = None
    human_review_enabled: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)


class RunAccepted(ApiModel):
    run_id: str
    conversation_id: str
    status: str
    events_url: str


class RunSummary(ApiModel):
    id: str
    conversation_id: str
    question: str
    status: str
    result_mode: str | None
    current_stage: str | None
    duration_ms: int | None
    created_at: datetime


class StageResponse(ApiModel):
    name: str
    attempt: int
    status: str
    message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    error_code: str | None = None
    error_message: str | None = None


class RunError(ApiModel):
    code: str
    message: str


class ArtifactResponse(ApiModel):
    id: str
    run_id: str
    stage: str
    type: str
    version: int
    summary: str | None
    payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime | None


class ReviewResponse(ApiModel):
    id: str
    run_id: str
    status: str
    reason: str | None
    review_comment: str | None
    plan: dict[str, Any] | None = None
    query: dict[str, Any] | None = None
    created_at: datetime
    reviewed_at: datetime | None


class AnalysisRunResponse(ApiModel):
    id: str
    conversation_id: str
    retry_of_run_id: str | None
    status: str
    result_mode: str | None
    question: str
    contextualized_question: str | None
    current_stage: str | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    stages: list[StageResponse]
    retrieval: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    queries: list[dict[str, Any]]
    analysis: dict[str, Any] | None = None
    review: ReviewResponse | None = None
    error: RunError | None = None


class ResultColumn(ApiModel):
    name: str
    label: str
    data_type: str


class ResultSetResponse(ApiModel):
    id: str
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    page: int
    page_size: int
    returned_rows: int
    total_rows: int
    truncated: bool


class ReviewDecision(ApiModel):
    comment: str | None = Field(default=None, max_length=500)


class ReviewRejectDecision(ApiModel):
    comment: str = Field(min_length=1, max_length=500)


class RunEvent(ApiModel):
    event_id: str
    conversation_id: str
    run_id: str
    seq: int
    type: str
    stage: str | None
    timestamp: datetime
    data: dict[str, Any]


class OperationResponse(ApiModel):
    ok: bool
    status: str
    message: str


class DatasourceTestResponse(ApiModel):
    datasource_id: str
    status: Literal["connected", "failed"]
    latency_ms: int
    message: str


ConversationDetail.model_rebuild()
