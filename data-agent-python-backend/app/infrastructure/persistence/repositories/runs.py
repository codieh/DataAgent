"""运行与阶段仓储（Run repository）。

管理分析运行（``AnalysisRunModel``）及其内部阶段（``StageRunModel``）的生命周期：

- 运行创建支持「幂等键」（防重复创建）与「重试」关联（``retry_of_run_id``）。
- 阶段支持创建/完成/失败三种状态转换，并自动计算耗时（``duration_ms``）。
- ``save_run`` 会自增 ``version`` 记录保存版本；当前没有按旧版本执行条件更新，
  因此它还不能检测并发写覆盖，不属于完整乐观锁实现。

阶段 ``attempt`` 由同 ``(run_id, stage)`` 已有最大尝试次数 +1 推导，支持重试。
"""

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
    """运行/阶段聚合的仓储实现。"""

    async def create_run(
        self,
        *,
        conversation: ConversationModel,
        question: str,
        human_review_enabled: bool,
        idempotency_key: str | None,
        retry_of_run_id: str | None = None,
    ) -> AnalysisRunModel:
        """创建一次分析运行，并将其记为所属对话的最近运行。"""
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
        """按幂等键查找运行（用于去重/幂等）。"""
        return await self.session.scalar(select(AnalysisRunModel).where(AnalysisRunModel.idempotency_key == key))

    async def get_run(self, run_id: str) -> AnalysisRunModel | None:
        """按 ID 获取运行。"""
        return await self.session.get(AnalysisRunModel, run_id)

    async def list_runs(self, conversation_id: str) -> list[AnalysisRunModel]:
        """列出某对话的全部运行，按创建时间倒序。"""
        statement = (
            select(AnalysisRunModel)
            .where(AnalysisRunModel.conversation_id == conversation_id)
            .order_by(AnalysisRunModel.created_at.desc())
        )
        return list((await self.session.scalars(statement)).all())

    async def save_run(self, run: AnalysisRunModel) -> AnalysisRunModel:
        """保存运行变更：版本计数自增，提交并刷新。

        注意：当前没有比较旧版本或检查受影响行数，只记录版本变化，不提供
        乐观并发冲突检测。
        """
        run.version += 1
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def create_stage(self, run_id: str, stage: str, message: str) -> StageRunModel:
        """为某运行创建（或重试）一个阶段执行记录，``attempt`` 自动递增。

        取同 ``(run_id, stage)`` 下已有最大 ``attempt`` 加 1，保证重试序号唯一递增。
        """
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
        """标记阶段为已完成，计算耗时（``duration_ms``）。"""
        now = utc_now()
        stage_run.status = "completed"
        stage_run.message = message
        stage_run.completed_at = now
        stage_run.duration_ms = elapsed_ms(stage_run.started_at, now)
        await self.session.commit()
        await self.session.refresh(stage_run)
        return stage_run

    async def fail_stage(self, stage_run: StageRunModel, error: Exception) -> StageRunModel:
        """标记阶段为失败，记录错误信息并计算耗时。"""
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
        """列出某运行下的全部阶段，按开始时间升序。"""
        statement = select(StageRunModel).where(StageRunModel.run_id == run_id).order_by(StageRunModel.started_at.asc())
        return list((await self.session.scalars(statement)).all())

    async def get_running_stage(self, run_id: str, stage: str) -> StageRunModel | None:
        """获取某运行下指定阶段当前处于 running 状态的记录（取最近一条）。"""
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
