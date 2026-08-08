"""API 总路由装配。

汇总各子模块（system / conversations / runs / results / reviews）的路由，
按顺序挂载到统一的根 ``APIRouter`` 上。调用方只需在 FastAPI 应用注册本 router 即可。
"""

from fastapi import APIRouter

from app.api.routes import conversations, results, reviews, runs, system


router = APIRouter()
router.include_router(system.router)
router.include_router(conversations.router)
router.include_router(runs.router)
router.include_router(results.router)
router.include_router(reviews.router)

