"""人工审核仓储（Review repository）。

管理人工审核检查点（``ReviewCheckpointModel``）。当分析运行启用人工审核时，会创建
检查点记录待审核状态，审核人完成/拒绝后更新 ``status`` 与 ``review_comment``。

侧重点：创建检查点、按 ID 或所属运行查询最新检查点、保存审核结果。
"""

from sqlalchemy import select

from app.infrastructure.persistence.models import ReviewCheckpointModel
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class ReviewRepository(RepositoryBase):
    """人工审核检查点聚合的仓储实现。"""

    async def create_review(
        self,
        *,
        run_id: str,
        plan_artifact_id: str,
        query_artifact_id: str | None,
        reason: str,
    ) -> ReviewCheckpointModel:
        """创建一条待审核检查点，关联计划产物（与可选查询产物）及触发原因。"""
        review = ReviewCheckpointModel(
            id=new_id("review"),
            run_id=run_id,
            plan_artifact_id=plan_artifact_id,
            query_artifact_id=query_artifact_id,
            reason=reason,
        )
        self.session.add(review)
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def get_review(self, review_id: str) -> ReviewCheckpointModel | None:
        """按 ID 获取审核检查点。"""
        return await self.session.get(ReviewCheckpointModel, review_id)

    async def get_review_by_run(self, run_id: str) -> ReviewCheckpointModel | None:
        """获取某运行最近的审核检查点（按创建时间倒序取第一条）。"""
        return await self.session.scalar(
            select(ReviewCheckpointModel)
            .where(ReviewCheckpointModel.run_id == run_id)
            .order_by(ReviewCheckpointModel.created_at.desc())
            .limit(1)
        )

    async def save_review(self, review: ReviewCheckpointModel) -> ReviewCheckpointModel:
        """提交审核检查点的字段修改（如状态、审核意见），并刷新返回。"""
        await self.session.commit()
        await self.session.refresh(review)
        return review

