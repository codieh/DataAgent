"""持久化 ORM 模型定义（基于 SQLAlchemy 2.0 风格 ``Mapped`` 注解）。

本模块集中定义平台的元数据实体（各聚合根对应的数据库表）：

- 对话域：``ConversationModel``、``MessageModel``、``UserCoreMemoryModel``、
  ``MemoryItemModel``、``ConversationSummaryStateModel``。
- 运行域：``AnalysisRunModel``（一次分析运行）、``StageRunModel``（运行内阶段）、
  ``RunEventModel``（运行事件流，按 ``seq`` 有序）、``ReviewCheckpointModel``（人工审核）。
- 产物域：``ArtifactModel``、``QueryModel``、``ResultSetModel``、``ToolCallModel``。

设计要点：
- 统一以 ``utc_now`` 作为时间字段默认值，保证时区一致（均为 UTC）。
- 大量使用外键 ``ondelete="CASCADE"``：删除父记录（对话/运行）时级联清理子表。
- 通过 ``UniqueConstraint`` 约束业务唯一键（如运行幂等键、阶段重试序号、工具调用序号）。
- JSON 列（``metadata_json``/``arguments_json`` 等）用于存储半结构化扩展数据。

所有模型均继承 ``database.Base``，由 ``initialize_database`` 统一建表。
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间，用作时间字段默认值。"""
    return datetime.now(timezone.utc)


def elapsed_ms(started_at: datetime | None, completed_at: datetime | None = None) -> int | None:
    """计算两个时间点之间的毫秒差（下限为 0）。

    用于统计运行/阶段/工具调用的耗时。``completed_at`` 缺省时取当前时刻。
    若传入的 datetime 缺少时区信息，会按 UTC 补全，避免朴素时间与感知时间相减报错。
    """
    if started_at is None:
        return None
    completed = completed_at or utc_now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=timezone.utc)
    return max(0, int((completed - started_at).total_seconds() * 1000))


class ConversationModel(Base):
    """对话聚合根：记录一次用户与 Agent 的会话。

    包含标题、所属 Agent/数据源、状态、摘要以及最近一次运行的引用。
    级联删除时会一并清理其下消息、记忆、运行等子记录。
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    agent_id: Mapped[str] = mapped_column(String(100), default="default-analysis")
    datasource_id: Mapped[str] = mapped_column(String(100), default="sales-db")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    last_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)


class MessageModel(Base):
    """对话中的单条消息（user/assistant/system 等）。

    ``run_id`` 关联产生该消息的分析运行；``content_type`` 标识内容格式（默认 markdown）。
    """

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(20), default="markdown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class UserCoreMemoryModel(Base):
    """用户核心记忆（跨对话持久化的用户画像/偏好）。

    以 ``profile_id`` 为主键（通常固定为 ``"default"``），内容为一整段文本，
    在被引用时会被作为 system 消息注入新对话。
    """

    __tablename__ = "user_core_memory"

    profile_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class MemoryItemModel(Base):
    """记忆条目：对话过程中抽取并保存的「事实/偏好」类记忆。

    ``kind`` 区分记忆类型（如 ``conversation_message`` 表示由单条消息派生的记忆）；
    ``source_message_id`` 唯一约束保证每条消息至多派生一条记忆；``importance`` 为
    重要度评分（0~1），用于记忆淘汰排序；``metadata_json`` 存放结构化附加信息。
    """

    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    datasource_id: Mapped[str] = mapped_column(String(100), default="sales-db", index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    source_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    importance: Mapped[float] = mapped_column(default=0.5)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ConversationSummaryStateModel(Base):
    """对话摘要状态：记录已摘要到的进度，支持增量摘要。

    以 ``conversation_id`` 为主键（一对一）。``summarized_message_count`` 表示
    已被纳入摘要的消息数量，下次摘要时只需处理新增部分。
    """

    __tablename__ = "conversation_summary_states"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    last_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summarized_message_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AnalysisRunModel(Base):
    """分析运行：一次完整的分析任务执行实例。

    保存用户原始问题、上下文化后的问题、运行状态/阶段、是否启用人工审核、
    起止时间与耗时、错误码与错误信息。``version`` 当前是每次 ``save_run`` 自增的
    版本计数；由于保存时没有按旧版本做条件更新，它不构成严格的乐观锁。
    ``event_seq`` 为事件序号计数器，由 ``EventRepository`` 递增生成事件序号。
    ``idempotency_key`` 唯一约束保证相同幂等键不会重复创建运行。
    """

    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    retry_of_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    question: Mapped[str] = mapped_column(Text)
    contextualized_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    result_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_review_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    event_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StageRunModel(Base):
    """运行内的阶段执行记录（如「规划」「查询」「可视化」等阶段）。

    同一 ``(run_id, stage)`` 可能因重试产生多条，用 ``attempt`` 区分；
    唯一约束 ``uq_stage_run_attempt`` 防止同一阶段同一次尝试重复插入。
    """

    __tablename__ = "stage_runs"
    __table_args__ = (UniqueConstraint("run_id", "stage", "attempt", name="uq_stage_run_attempt"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ToolCallModel(Base):
    """工具调用记录：Agent 在运行中发起的每一次工具（function call）调用。

    两条唯一约束：``uq_tool_call_run_provider_id``（同一 run 内某 ``tool_call_id``
    唯一，避免重复记录）与 ``uq_tool_call_run_sequence``（同一 run 内序号 ``sequence``
    唯一，保证调用顺序稳定）。``arguments_json``/``result_json``/``error_json`` 均为
    JSON，分别存放入参、返回结果与错误信息。
    """

    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint("run_id", "tool_call_id", name="uq_tool_call_run_provider_id"),
        UniqueConstraint("run_id", "sequence", name="uq_tool_call_run_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    tool_call_id: Mapped[str] = mapped_column(String(200))
    sequence: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(100), index=True)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ArtifactModel(Base):
    """产物：运行各阶段产出的结构化结果（如图表配置、SQL 计划、可视化等）。

    ``stage`` 标识所属阶段，``type`` 标识产物类型，``payload`` 为具体 JSON 内容，
    ``file_path`` 可选指向外部文件，``expires_at`` 用于过期清理。
    """

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QueryModel(Base):
    """SQL 查询记录：运行中对业务库发起的每一次查询尝试。

    ``attempt`` 表示重试次数；``row_count`` 为返回行数；``result_set_id`` 关联
    结果集；``safety`` 存放安全策略校验结果；``error`` 为失败信息。``status`` 为
    该次查询的最终状态。
    """

    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sql: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    result_set_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    safety: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ResultSetModel(Base):
    """查询结果集：一条查询的结果数据（列定义 + 行数据）。

    ``columns``/``rows`` 为 JSON 存储的实际数据；``total_rows`` 为总行数（可能
    大于已存 ``rows``）；``truncated`` 指示是否被截断；``storage_type`` 标识存储方式
    （默认 ``sqlite``，大数据量可外置为文件，见 ``file_path``）；``expires_at`` 用于清理。
    """

    __tablename__ = "result_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_type: Mapped[str] = mapped_column(String(20), default="sqlite")
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewCheckpointModel(Base):
    """人工审核检查点：当运行启用人工审核时，记录待审核状态与结果。

    ``status`` 为审核状态（默认 ``waiting``）；``plan_artifact_id``/``query_artifact_id``
    分别关联待审核的计划与查询产物；``reason`` 为触发审核原因；``review_comment`` 为
    审核人意见；``reviewed_at`` 为审核完成时间。
    """

    __tablename__ = "review_checkpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="waiting")
    plan_artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    query_artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunEventModel(Base):
    """运行事件流：以追加方式记录运行过程中的流式事件。

    ``seq`` 为事件序号（同 ``run_id`` 内唯一且递增，见 ``uq_run_event_seq``），
    用于前端按序推送/增量拉取；``type`` 为事件类型，``stage`` 为所属阶段，
    ``data`` 为事件负载 JSON。
    """

    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_event_seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(64), index=True)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
