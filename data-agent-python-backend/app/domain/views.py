"""只读视图对象（View Models）。

这些 dataclass 是领域层组装后返回给接口层的数据结构，仅承载展示所需的数据，
不含行为。使用 slots=True 降低内存占用（视图对象可能大量创建于列表查询中）。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ReviewView:
    """人工审核视图：包含审核状态及其关联的计划/查询产物。"""

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
    """一次分析运行的完整前端视图。"""

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
    """会话详情视图：会话本体 + 其消息列表 + 运行列表。"""

    conversation: Any
    messages: list[Any]
    runs: list[Any]

