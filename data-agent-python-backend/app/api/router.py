from fastapi import APIRouter

from app.api.routes import conversations, results, reviews, runs, system


router = APIRouter()
router.include_router(system.router)
router.include_router(conversations.router)
router.include_router(runs.router)
router.include_router(results.router)
router.include_router(reviews.router)

