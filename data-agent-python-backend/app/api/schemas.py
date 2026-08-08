"""API 响应/请求数据模型（Pydantic）。

集中定义所有对外 JSON 结构。基类 ``ApiModel`` 统一约定：
- 使用 snake_case 字段名，对外序列化为 camelCase（通过 ``alias_generator``）；
- ``populate_by_name=True`` 允许请求同时按原名或别名赋值；
- ``from_attributes=True`` 支持直接从 ORM 对象填充。

约定：请求体以 ``*Create`` / ``*Update`` / ``*Decision`` 命名，响应以 ``*Response`` 命名。
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    """把 snake_case 字段名转换为 camelCase（首段保持小写）。"""
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    """所有 API 模型的基类，约定命名风格与 ORM 兼容行为。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class AgentProfile(ApiModel):
    """智能体档案（用于前端展示可选的分析智能体）。"""

    id: str
    name: str
    description: str
    is_default: bool = False


class DatasourceSummary(ApiModel):
    """数据源概览（id/名称/类型/连接状态）。"""

    id: str
    name: str
    type: str
    status: str
    is_default: bool = False


class BootstrapResponse(ApiModel):
    """前端首屏引导数据：默认智能体、智能体列表、数据源、功能开关与推荐问题。"""

    default_agent_id: str
    agents: list[AgentProfile]
    recommended_questions: list[str]
    datasources: list[DatasourceSummary]
    features: dict[str, bool]


class HealthResponse(ApiModel):
    """健康检查响应：服务与数据库状态、版本与时间戳。"""

    status: str
    database: str
    version: str
    timestamp: datetime


class ConversationCreate(ApiModel):
    """创建会话请求体。"""

    title: str | None = Field(default=None, max_length=200)
    agent_id: str = "default-analysis"
    datasource_id: str = "sales-db"


class ConversationUpdate(ApiModel):
    """更新会话请求体（所有字段可选）。"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    agent_id: str | None = None
    datasource_id: str | None = None


class MessageResponse(ApiModel):
    """会话中的单条消息。"""

    id: str
    conversation_id: str
    run_id: str | None
    role: str
    content: str
    content_type: str
    created_at: datetime


class ConversationSummary(ApiModel):
    """会话概览卡片（列表与详情共用的精简字段）。"""

    id: str
    title: str
    agent_id: str
    datasource_id: str
    status: str
    last_run_id: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    """会话详情：在概览基础上补充摘要、消息列表与运行列表。"""

    summary: str | None
    messages: list[MessageResponse]
    runs: list["RunSummary"]


class ConversationListResponse(ApiModel):
    """会话列表分页响应（含游标以支持后续分页）。"""

    items: list[ConversationSummary]
    next_cursor: str | None = None


class MemoryItemResponse(ApiModel):
    """单条长期记忆项。"""

    id: str
    kind: str
    content: str
    importance: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(ApiModel):
    """长期记忆列表响应。"""

    items: list[MemoryItemResponse]


class RunCreate(ApiModel):
    """发起一次分析运行（run）的请求体。"""

    query: str = Field(min_length=1, max_length=20_000)
    agent_id: str | None = None
    datasource_id: str | None = None
    human_review_enabled: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)


class RunAccepted(ApiModel):
    """运行已受理的响应（202 Accepted），含事件流URL供前端轮询/订阅。"""

    run_id: str
    conversation_id: str
    status: str
    events_url: str


class RunSummary(ApiModel):
    """运行概览（列表与详情共用的精简字段）。"""

    id: str
    conversation_id: str
    question: str
    status: str
    result_mode: str | None
    current_stage: str | None
    duration_ms: int | None
    created_at: datetime


class StageResponse(ApiModel):
    """运行单个阶段（stage）的状态与耗时、错误信息。"""

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
    """运行失败时的错误码与消息。"""

    code: str
    message: str


class ArtifactResponse(ApiModel):
    """运行产出的产物（artifact），payload 为任意结构化的阶段结果。"""

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
    """人工评审记录：状态、理由、评审意见，以及被评审的 plan/query 快照。"""

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
    """运行的完整详情响应，内联展开阶段、检索、计划、查询、分析、评审与错误。"""

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
    """结果集中的列定义（名称/显示名/数据类型）。"""

    name: str
    label: str
    data_type: str


class ResultSetResponse(ApiModel):
    """结果集分页响应。"""

    id: str
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    page: int
    page_size: int
    returned_rows: int
    total_rows: int
    truncated: bool


class ReviewDecision(ApiModel):
    """通过评审的请求体（评论可选）。"""

    comment: str | None = Field(default=None, max_length=500)


class ReviewRejectDecision(ApiModel):
    """驳回评审的请求体（评论必填）。"""

    comment: str = Field(min_length=1, max_length=500)


class RunEvent(ApiModel):
    """运行事件（用于 SSE 推送的单个事件负载）。"""

    event_id: str
    conversation_id: str
    run_id: str
    # 仅持久事件拥有可续传序号；Token 增量等临时事件为 None。
    seq: int | None
    type: str
    stage: str | None
    timestamp: datetime
    data: dict[str, Any]


class OperationResponse(ApiModel):
    """通用操作结果响应（删除/取消等）。"""

    ok: bool
    status: str
    message: str


class DatasourceTestResponse(ApiModel):
    """数据源连通性测试结果：状态、延迟与说明信息。"""

    datasource_id: str
    status: Literal["connected", "failed"]
    latency_ms: int
    message: str


ConversationDetail.model_rebuild()
