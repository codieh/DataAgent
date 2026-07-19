"""FastAPI 应用入口。

负责创建应用实例、注册路由与中间件、配置跨域（CORS），并通过 lifespan 在
启动/关闭时初始化数据库、图运行时、任务注册表，并恢复被中断的分析任务。
同时配置了 HTTP 请求级日志与根日志器。
"""

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
from app.observability.logging_setup import configure_logging


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 统一配置根日志，确保模型输入/输出与工具调用日志可见。
    configure_logging(
        file_path=settings.log_file_path if settings.log_file_enabled else None,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
    )
    logger.info(
        "application configuration: llmProvider=openai model=%s baseUrl=%s apiKeyConfigured=%s "
        "llmRawResponseLogging=%s llmIoLogging=%s llmThinkingEnabled=%s "
        "productDatabaseDriver=%s logFile=%s",
        settings.llm_model,
        settings.llm_base_url,
        bool(settings.llm_api_key.strip()),
        settings.llm_log_responses,
        settings.llm_log_io,
        settings.llm_thinking_enabled,
        settings.product_database_url.split(":", 1)[0],
        str(settings.log_file_path) if settings.log_file_enabled else "disabled",
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
