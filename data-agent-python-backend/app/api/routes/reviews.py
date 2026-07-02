from fastapi import APIRouter

from app.api.dependencies import SessionDependency
from app.api.presenters import review_response
from app.api.schemas import ReviewDecision, ReviewRejectDecision, ReviewResponse
from app.application import RunViewService
from app.application.run_commands import ReviewCommandService
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.repository import Repository


router = APIRouter(prefix="/reviews", tags=["reviews"])


async def load_review(review_id: str, session: SessionDependency) -> ReviewResponse:
    repository = Repository(session)
    review = await repository.get_review(review_id)
    if not review:
        raise ResourceNotFoundError("review", review_id)
    return review_response(await RunViewService(session).review_view(review))


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(review_id: str, session: SessionDependency) -> ReviewResponse:
    return await load_review(review_id, session)


@router.post("/{review_id}/approve", response_model=ReviewResponse)
async def approve_review(review_id: str, body: ReviewDecision, session: SessionDependency) -> ReviewResponse:
    await ReviewCommandService(Repository(session)).decide(review_id, approved=True, comment=body.comment)
    return await load_review(review_id, session)


@router.post("/{review_id}/reject", response_model=ReviewResponse)
async def reject_review(review_id: str, body: ReviewRejectDecision, session: SessionDependency) -> ReviewResponse:
    await ReviewCommandService(Repository(session)).decide(review_id, approved=False, comment=body.comment)
    return await load_review(review_id, session)

