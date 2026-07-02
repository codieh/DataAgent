from sqlalchemy import func, select

from app.infrastructure.persistence.models import (
    AnalysisRunModel,
    ConversationModel,
    StageRunModel,
    elapsed_ms,
    utc_now,
)
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class RunRepository(RepositoryBase):
    async def create_run(
        self,
        *,
        conversation: ConversationModel,
        question: str,
        human_review_enabled: bool,
        idempotency_key: str | None,
        retry_of_run_id: str | None = None,
    ) -> AnalysisRunModel:
        run = AnalysisRunModel(
            id=new_id("run"),
            conversation_id=conversation.id,
            retry_of_run_id=retry_of_run_id,
            idempotency_key=idempotency_key,
            question=question,
            human_review_enabled=human_review_enabled,
        )
        self.session.add(run)
        conversation.last_run_id = run.id
        conversation.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def find_run_by_idempotency_key(self, key: str) -> AnalysisRunModel | None:
        return await self.session.scalar(select(AnalysisRunModel).where(AnalysisRunModel.idempotency_key == key))

    async def get_run(self, run_id: str) -> AnalysisRunModel | None:
        return await self.session.get(AnalysisRunModel, run_id)

    async def list_runs(self, conversation_id: str) -> list[AnalysisRunModel]:
        statement = (
            select(AnalysisRunModel)
            .where(AnalysisRunModel.conversation_id == conversation_id)
            .order_by(AnalysisRunModel.created_at.desc())
        )
        return list((await self.session.scalars(statement)).all())

    async def save_run(self, run: AnalysisRunModel) -> AnalysisRunModel:
        run.version += 1
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def create_stage(self, run_id: str, stage: str, message: str) -> StageRunModel:
        attempt = (
            await self.session.scalar(
                select(func.coalesce(func.max(StageRunModel.attempt), 0)).where(
                    StageRunModel.run_id == run_id, StageRunModel.stage == stage
                )
            )
        ) + 1
        stage_run = StageRunModel(
            id=new_id("stage"),
            run_id=run_id,
            stage=stage,
            attempt=attempt,
            status="running",
            message=message,
            started_at=utc_now(),
        )
        self.session.add(stage_run)
        await self.session.commit()
        await self.session.refresh(stage_run)
        return stage_run

    async def finish_stage(self, stage_run: StageRunModel, message: str) -> StageRunModel:
        now = utc_now()
        stage_run.status = "completed"
        stage_run.message = message
        stage_run.completed_at = now
        stage_run.duration_ms = elapsed_ms(stage_run.started_at, now)
        await self.session.commit()
        await self.session.refresh(stage_run)
        return stage_run

    async def fail_stage(self, stage_run: StageRunModel, error: Exception) -> StageRunModel:
        now = utc_now()
        stage_run.status = "failed"
        stage_run.message = str(error) or error.__class__.__name__
        stage_run.error_code = error.__class__.__name__
        stage_run.error_message = str(error) or error.__class__.__name__
        stage_run.completed_at = now
        stage_run.duration_ms = elapsed_ms(stage_run.started_at, now)
        await self.session.commit()
        await self.session.refresh(stage_run)
        return stage_run

    async def list_stages(self, run_id: str) -> list[StageRunModel]:
        statement = select(StageRunModel).where(StageRunModel.run_id == run_id).order_by(StageRunModel.started_at.asc())
        return list((await self.session.scalars(statement)).all())

    async def get_running_stage(self, run_id: str, stage: str) -> StageRunModel | None:
        return await self.session.scalar(
            select(StageRunModel)
            .where(
                StageRunModel.run_id == run_id,
                StageRunModel.stage == stage,
                StageRunModel.status == "running",
            )
            .order_by(StageRunModel.started_at.desc())
            .limit(1)
        )
