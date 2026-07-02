from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ResourceNotFoundError
from app.domain.views import ReviewView, RunView
from app.infrastructure.persistence.models import ReviewCheckpointModel
from app.infrastructure.persistence.repository import Repository


class RunViewService:
    def __init__(self, session: AsyncSession):
        self.repository = Repository(session)

    async def build(self, run_id: str) -> RunView:
        run = await self.repository.get_run(run_id)
        if not run:
            raise ResourceNotFoundError("run", run_id)
        stages = await self.repository.list_stages(run_id)
        artifacts = await self.repository.list_artifacts(run_id)
        queries = await self.repository.list_queries(run_id)
        review = await self.repository.get_review_by_run(run_id)
        artifacts_by_type = {artifact.type: artifact for artifact in artifacts}
        return RunView(
            id=run.id,
            conversation_id=run.conversation_id,
            retry_of_run_id=run.retry_of_run_id,
            status=run.status,
            result_mode=run.result_mode,
            question=run.question,
            contextualized_question=run.contextualized_question,
            current_stage=run.current_stage,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_ms=run.duration_ms,
            stages=[
                {
                    "name": stage.stage,
                    "attempt": stage.attempt,
                    "status": stage.status,
                    "message": stage.message,
                    "started_at": stage.started_at,
                    "completed_at": stage.completed_at,
                    "duration_ms": stage.duration_ms,
                    "error_code": stage.error_code,
                    "error_message": stage.error_message,
                }
                for stage in stages
            ],
            retrieval=artifacts_by_type["retrieval"].payload if "retrieval" in artifacts_by_type else None,
            plan=artifacts_by_type["plan"].payload if "plan" in artifacts_by_type else None,
            queries=[
                {
                    "id": query.id,
                    "stepId": query.step_id,
                    "sql": query.sql,
                    "status": query.status,
                    "attempt": query.attempt,
                    "durationMs": query.duration_ms,
                    "rowCount": query.row_count,
                    "resultSetId": query.result_set_id,
                    "safety": query.safety,
                    "error": query.error,
                }
                for query in queries
            ],
            analysis=artifacts_by_type["analysis"].payload if "analysis" in artifacts_by_type else None,
            review=await self.review_view(review) if review else None,
            error={"code": run.error_code or "run_failed", "message": run.error_message or "unknown error"}
            if run.error_message
            else None,
        )

    async def artifact(self, artifact_id: str):
        artifact = await self.repository.get_artifact(artifact_id)
        if not artifact:
            raise ResourceNotFoundError("artifact", artifact_id)
        return artifact

    async def review_view(self, review: ReviewCheckpointModel) -> ReviewView:
        plan = await self.repository.get_artifact(review.plan_artifact_id) if review.plan_artifact_id else None
        query = await self.repository.get_artifact(review.query_artifact_id) if review.query_artifact_id else None
        return ReviewView(
            id=review.id,
            run_id=review.run_id,
            status=review.status,
            reason=review.reason,
            review_comment=review.review_comment,
            plan=plan.payload if plan else None,
            query=query.payload if query else None,
            created_at=review.created_at,
            reviewed_at=review.reviewed_at,
        )

