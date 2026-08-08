"""FastAPI 应用入口。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import build_router
from app.application.events import EventBroker
from app.config import get_settings
from app.infrastructure.datasource.mysql import BusinessDatabase
from app.infrastructure.persistence.database import ControlDatabase
from app.infrastructure.results.store import ResultStore
from app.infrastructure.sdk.runtime import SDKRuntime

control_database = ControlDatabase()
result_store = ResultStore()
event_broker = EventBroker(control_database)
runtime = SDKRuntime(control_database, BusinessDatabase(), result_store, event_broker)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.prepare_directories()
    logger.info(
        "application configuration: model=%s baseUrl=%s apiKeyConfigured=%s productDatabaseConfigured=%s",
        settings.claude_model,
        settings.anthropic_base_url,
        bool(settings.anthropic_api_key.strip()),
        bool(settings.product_database_url.strip() or settings.tenant_database_urls),
    )
    await control_database.initialize()
    yield


app = FastAPI(title="DataAgent Claude SDK", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Tenant-ID", "X-User-ID", "X-Conversation-ID", "X-Request-ID"],
)
app.include_router(build_router(control_database, runtime, event_broker, result_store))
