"""展示转换器（presenters）。

把领域/应用层返回的视图对象（View）或 SQLAlchemy 模型转换为 API 响应用的
Pydantic 模型。这一层负责「字段映射」「忽略系统消息」「按需展开关联对象」
等展示逻辑，使路由处理函数保持简洁。
"""

from app.api.schemas import (
    AnalysisRunResponse,
    ArtifactResponse,
    ConversationDetail,
    ConversationSummary,
    MessageResponse,
    ReviewResponse,
    RunError,
    RunEvent,
    RunSummary,
    StageResponse,
)
from app.domain.views import ConversationView, ReviewView, RunView


def conversation_summary(conversation) -> ConversationSummary:
    """会话概览：直接由模型字段驱动校验转换。"""
    return ConversationSummary.model_validate(conversation)


def run_summary(run) -> RunSummary:
    """运行概览：由模型字段驱动校验转换。"""
    return RunSummary.model_validate(run)


def conversation_detail(view: ConversationView) -> ConversationDetail:
    """会话详情：合并概览字段 + 消息列表（剔除 system 消息）+ 运行列表。"""
    return ConversationDetail(
        **conversation_summary(view.conversation).model_dump(),
        summary=view.conversation.summary,
        # 系统提示词不应暴露给前端，按 role 过滤
        messages=[MessageResponse.model_validate(message) for message in view.messages if message.role != "system"],
        runs=[run_summary(run) for run in view.runs],
    )


def review_response(view: ReviewView) -> ReviewResponse:
    """人工评审记录：由视图对象直接校验转换。"""
    return ReviewResponse.model_validate(view)


def run_response(view: RunView) -> AnalysisRunResponse:
    """运行详情：把运行视图完整展开为响应模型，关联评审/错误按需内联。"""
    return AnalysisRunResponse(
        id=view.id,
        conversation_id=view.conversation_id,
        retry_of_run_id=view.retry_of_run_id,
        status=view.status,
        result_mode=view.result_mode,
        question=view.question,
        contextualized_question=view.contextualized_question,
        current_stage=view.current_stage,
        started_at=view.started_at,
        completed_at=view.completed_at,
        duration_ms=view.duration_ms,
        stages=[StageResponse.model_validate(stage) for stage in view.stages],
        retrieval=view.retrieval,
        plan=view.plan,
        queries=view.queries,
        analysis=view.analysis,
        # 存在评审对象时才内联评审响应，否则置空
        review=review_response(view.review) if view.review else None,
        error=RunError.model_validate(view.error) if view.error else None,
    )


def artifact_response(artifact) -> ArtifactResponse:
    """产物（artifact）：由模型字段直接校验转换。"""
    return ArtifactResponse.model_validate(artifact)


def event_response(event) -> RunEvent:
    """运行事件：把持久层事件映射为 SSE 推送用的事件响应模型。"""
    return RunEvent(
        event_id=event.id,
        conversation_id=event.conversation_id,
        run_id=event.run_id,
        seq=event.seq,
        type=event.type,
        stage=event.stage,
        timestamp=event.created_at,
        data=event.data,
    )
