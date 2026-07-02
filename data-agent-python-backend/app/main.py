from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.api.errors import install_error_handlers
from app.application import recover_interrupted_runs, task_registry
from app.application.executor import graph_runtime
from app.config import get_settings
from app.infrastructure.persistence.database import close_database, initialize_database


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "application configuration: llmProvider=openai model=%s baseUrl=%s apiKeyConfigured=%s "
        "llmRawResponseLogging=%s llmThinkingEnabled=%s productDatabaseDriver=%s",
        settings.llm_model,
        settings.llm_base_url,
        bool(settings.llm_api_key.strip()),
        settings.llm_log_responses,
        settings.llm_thinking_enabled,
        settings.product_database_url.split(":", 1)[0],
    )
    await initialize_database()
    await graph_runtime.startup()
    await recover_interrupted_runs()
    yield
    await task_registry.shutdown()
    await graph_runtime.shutdown()
    await close_database()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)
install_error_handlers(app)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http request failed: requestId=%s method=%s path=%s durationMs=%d",
            request_id,
            request.method,
            request.url.path,
            int((perf_counter() - started) * 1000),
        )
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "http request completed: requestId=%s method=%s path=%s status=%d durationMs=%d",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        int((perf_counter() - started) * 1000),
    )
    return response


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": f"{settings.api_prefix}/health"}
