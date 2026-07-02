from typing import Any, TypedDict


class AnalysisState(TypedDict, total=False):
    run_id: str
    conversation_id: str
    query: str
    contextualized_query: str
    human_review_enabled: bool
    human_feedback: dict[str, Any]
    intent: str
    execution_path: str
    knowledge: dict[str, list[dict[str, Any]]]
    schema: dict[str, Any]
    schema_reasons: dict[str, str]
    plan: dict[str, Any]
    selected_tables: list[str]
    sql: str
    sql_explanation: str
    safety: dict[str, Any]
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    retry_count: int
    sql_error: str | None
    result_mode: str | None
    analysis: dict[str, Any]
    error: str | None
    security: dict[str, Any]
