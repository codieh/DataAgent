from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ReviewView:
    id: str
    run_id: str
    status: str
    reason: str | None
    review_comment: str | None
    plan: dict[str, Any] | None
    query: dict[str, Any] | None
    created_at: datetime
    reviewed_at: datetime | None


@dataclass(slots=True)
class RunView:
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
    stages: list[dict[str, Any]]
    retrieval: dict[str, Any] | None
    plan: dict[str, Any] | None
    queries: list[dict[str, Any]]
    analysis: dict[str, Any] | None
    review: ReviewView | None
    error: dict[str, str] | None


@dataclass(slots=True)
class ConversationView:
    conversation: Any
    messages: list[Any]
    runs: list[Any]

