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
    return ConversationSummary.model_validate(conversation)


def run_summary(run) -> RunSummary:
    return RunSummary.model_validate(run)


def conversation_detail(view: ConversationView) -> ConversationDetail:
    return ConversationDetail(
        **conversation_summary(view.conversation).model_dump(),
        summary=view.conversation.summary,
        messages=[MessageResponse.model_validate(message) for message in view.messages],
        runs=[run_summary(run) for run in view.runs],
    )


def review_response(view: ReviewView) -> ReviewResponse:
    return ReviewResponse.model_validate(view)


def run_response(view: RunView) -> AnalysisRunResponse:
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
        review=review_response(view.review) if view.review else None,
        error=RunError.model_validate(view.error) if view.error else None,
    )


def artifact_response(artifact) -> ArtifactResponse:
    return ArtifactResponse.model_validate(artifact)


def event_response(event) -> RunEvent:
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

