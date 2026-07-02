from sqlalchemy import select

from app.infrastructure.persistence.models import ReviewCheckpointModel
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class ReviewRepository(RepositoryBase):
    async def create_review(
        self,
        *,
        run_id: str,
        plan_artifact_id: str,
        query_artifact_id: str | None,
        reason: str,
    ) -> ReviewCheckpointModel:
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
        return await self.session.get(ReviewCheckpointModel, review_id)

    async def get_review_by_run(self, run_id: str) -> ReviewCheckpointModel | None:
        return await self.session.scalar(
            select(ReviewCheckpointModel)
            .where(ReviewCheckpointModel.run_id == run_id)
            .order_by(ReviewCheckpointModel.created_at.desc())
            .limit(1)
        )

    async def save_review(self, review: ReviewCheckpointModel) -> ReviewCheckpointModel:
        await self.session.commit()
        await self.session.refresh(review)
        return review

