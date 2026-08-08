"""运行视图组装服务。

将一次分析运行的各类持久化记录（运行、阶段、产物、查询、审核）聚合为
面向前端的视图对象（RunView / ReviewView）。该服务为只读，不改变任何状态。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ResourceNotFoundError
from app.domain.views import ReviewView, RunView
from app.infrastructure.persistence.models import ReviewCheckpointModel
from app.infrastructure.persistence.repository import Repository


class RunViewService:
    """运行视图服务：组装运行详情与产物/审核视图。"""

    def __init__(self, session: AsyncSession):
        self.repository = Repository(session)

    async def build(self, run_id: str) -> RunView:
        """组装一次运行的完整前端视图。

        参数:
            run_id: 目标运行 ID（不存在则抛 ResourceNotFoundError）。
        返回:
            聚合运行状态、阶段列表、各类产物、查询与分析结果的 RunView。
        说明:
            产物按类型去重后嵌入对应字段（retrieval / plan / analysis 等），
            仅保留每个类型最新的一条。
        """
        run = await self.repository.get_run(run_id)
        if not run:
            raise ResourceNotFoundError("run", run_id)
        stages = await self.repository.list_stages(run_id)
        artifacts = await self.repository.list_artifacts(run_id)
        queries = await self.repository.list_queries(run_id)
        review = await self.repository.get_review_by_run(run_id)
        # 按产物类型建立索引，便于后续取「最新一条」嵌入视图字段。
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
            # 逐阶段展开为标准字典结构供前端渲染。
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
            # 仅当存在对应类型产物时才嵌入 payload。
            retrieval=artifacts_by_type["retrieval"].payload if "retrieval" in artifacts_by_type else None,
            plan=artifacts_by_type["plan"].payload if "plan" in artifacts_by_type else None,
            # 每条查询展开为前端所需字段（含安全信息、结果集 ID 等）。
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
            # 仅当运行时产生错误信息才暴露 error 字段，且缺省给出兜底文案。
            error={"code": run.error_code or "run_failed", "message": run.error_message or "unknown error"}
            if run.error_message
            else None,
        )

    async def artifact(self, artifact_id: str):
        """按产物 ID 直接获取原始产物记录（不存在则抛 ResourceNotFoundError）。"""
        artifact = await self.repository.get_artifact(artifact_id)
        if not artifact:
            raise ResourceNotFoundError("artifact", artifact_id)
        return artifact

    async def review_view(self, review: ReviewCheckpointModel) -> ReviewView:
        """把审核记录连同其关联的计划/查询产物组装为 ReviewView。"""
        # 仅当审核记录关联了产物 ID 时才回查对应产物 payload。
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

