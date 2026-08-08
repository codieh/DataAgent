"""会话、运行和结果 API。"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.application.events import EventBroker
from app.config import get_settings
from app.domain.errors import AppError
from app.domain.models import TenantContext
from app.infrastructure.persistence.database import ControlDatabase
from app.infrastructure.results.store import ResultStore
from app.infrastructure.sdk.runtime import SDKRuntime


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class CreateRunRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)


def build_router(database: ControlDatabase, runtime: SDKRuntime, broker: EventBroker, results: ResultStore) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health")
    async def health() -> dict[str, str]:
        settings = get_settings()
        return {
            "status": "ok",
            "service": "data-agent-claude-sdk",
            "llm_configured": str(bool(settings.anthropic_api_key.strip() and settings.anthropic_base_url.strip())).lower(),
            "database_configured": str(bool(settings.product_database_url.strip() or settings.tenant_database_urls)).lower(),
            "model": settings.claude_model,
        }

    @router.post("/conversations")
    async def create_conversation(
        body: CreateConversationRequest,
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
        user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
    ) -> dict[str, str]:
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="必须提供 X-Tenant-ID 和 X-User-ID")
        conversation_id = f"conv_{uuid4().hex}"
        context = TenantContext(tenant_id, user_id, conversation_id, f"bootstrap_{uuid4().hex}")
        await database.create_conversation(context, body.title)
        return {"conversation_id": conversation_id, "tenant_id": tenant_id, "user_id": user_id}

    @router.get("/conversations")
    async def list_conversations(
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
        user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict:
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="必须提供租户和用户身份")
        return {"conversations": await database.list_conversations(tenant_id, user_id, limit)}

    @router.get("/conversations/{conversation_id}")
    async def get_conversation(
        conversation_id: str,
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
        user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
    ) -> dict:
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="必须提供租户和用户身份")
        conversation = await database.get_conversation(tenant_id, conversation_id)
        if not conversation or conversation["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {
            "conversation": conversation,
            "messages": await database.list_messages(tenant_id, user_id, conversation_id),
        }

    @router.post("/conversations/{conversation_id}/runs", status_code=202)
    async def create_run(
        conversation_id: str,
        body: CreateRunRequest,
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
        user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
    ) -> dict[str, str]:
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="必须提供 X-Tenant-ID 和 X-User-ID")
        conversation = await database.get_conversation(tenant_id, conversation_id)
        if not conversation or conversation["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        run_id = f"run_{uuid4().hex}"
        context = TenantContext(tenant_id, user_id, conversation_id, run_id)
        try:
            await runtime.submit(context, body.question)
        except AppError as error:
            raise HTTPException(status_code=409, detail={"code": error.code, "message": error.message}) from error
        return {"run_id": run_id, "conversation_id": conversation_id, "status": "running"}

    @router.get("/runs/{run_id}")
    async def get_run(
        run_id: str,
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
        user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
    ) -> dict:
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="必须提供租户和用户身份")
        run = await database.get_run(tenant_id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="运行不存在")
        conversation = await database.get_conversation(tenant_id, run["conversation_id"])
        if not conversation or conversation["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="运行不存在")
        return {
            "run": run,
            # REST 快照与 SSE 使用同一套事件信封，避免前端恢复历史 Run
            # 时在 payload/data 两套字段之间分支处理。
            "events": [_event_view(event) for event in await database.list_events(tenant_id, run_id)],
            "tool_calls": await database.list_tool_calls(tenant_id, run_id),
        }

    @router.post("/runs/{run_id}/cancel")
    async def cancel_run(
        run_id: str,
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
        user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
    ) -> dict[str, str]:
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="必须提供租户和用户身份")
        run = await database.get_run(tenant_id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="运行不存在")
        conversation = await database.get_conversation(tenant_id, run["conversation_id"])
        if not conversation or conversation["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="运行不存在")
        context = TenantContext(tenant_id, user_id, run["conversation_id"], run_id)
        await runtime.cancel(context)
        return {"run_id": run_id, "status": "cancelled"}

    @router.get("/runs/{run_id}/events")
    async def stream_events(
        run_id: str,
        request: Request,
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
        user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
        after_seq: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="必须提供租户和用户身份")
        run = await database.get_run(tenant_id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="运行不存在")
        conversation = await database.get_conversation(tenant_id, run["conversation_id"])
        if not conversation or conversation["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="运行不存在")

        async def stream():
            sequence = after_seq
            async with broker.subscribe(run_id) as queue:
                for event in await database.list_events(tenant_id, run_id, sequence):
                    sequence = max(sequence, int(event["seq"]))
                    yield _sse(event)
                current = await database.get_run(tenant_id, run_id)
                if current and current["status"] in {"completed", "failed", "cancelled"}:
                    return
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=get_settings().sse_heartbeat_seconds)
                    except TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    if event.get("type") == "stream.overflow":
                        yield _sse({"seq": sequence, "type": "stream.overflow", "payload": {"resume": True}})
                        return
                    if event.get("ephemeral"):
                        # 逐 token 增量不落库、没有 seq，直接透传且不推进续传游标。
                        yield _sse(event)
                        continue
                    if int(event["seq"]) <= sequence:
                        continue
                    sequence = int(event["seq"])
                    yield _sse(event)
                    if event["type"] in {"run.completed", "run.failed", "run.cancelled"}:
                        return

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/result-sets/{result_id}")
    async def read_result(
        result_id: str,
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
        user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
        conversation_id: Annotated[str | None, Header(alias="X-Conversation-ID")] = None,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict:
        if not tenant_id or not user_id or not conversation_id:
            raise HTTPException(status_code=401, detail="必须提供租户和会话身份")
        conversation = await database.get_conversation(tenant_id, conversation_id)
        if not conversation or conversation["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="结果不存在")
        metadata = await database.get_result_set_by_id(tenant_id, conversation_id, result_id)
        return await results.read(metadata["file_path"], offset=offset, limit=limit)

    @router.get("/result-sets/{result_id}/download")
    async def download_result(
        result_id: str,
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
        user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
        conversation_id: Annotated[str | None, Header(alias="X-Conversation-ID")] = None,
        format: str = Query(default="json", pattern="^(json|csv)$"),
    ) -> FileResponse:
        if not tenant_id or not user_id or not conversation_id:
            raise HTTPException(status_code=401, detail="必须提供租户和会话身份")
        conversation = await database.get_conversation(tenant_id, conversation_id)
        if not conversation or conversation["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="结果不存在")
        metadata = await database.get_result_set_by_id(tenant_id, conversation_id, result_id)
        path = Path(metadata["file_path"])
        if format == "csv":
            path = path.with_suffix(".csv")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="结果文件不存在")
        media_type = "text/csv; charset=utf-8" if format == "csv" else "application/json"
        return FileResponse(path, media_type=media_type, filename=f"{result_id}.{format}")

    return router


def _sse(event: dict) -> str:
    ephemeral = bool(event.get("ephemeral"))
    payload = {
        "event_id": event.get("event_id"),
        "seq": event.get("seq"),
        "type": event.get("type"),
        "timestamp": datetime.now(UTC).isoformat(),
        "data": event.get("payload", {}),
        "ephemeral": ephemeral,
    }
    lines = [f"event: {event.get('type', 'message')}"]
    # 增量事件没有 seq，不能写 id：空 id 会重置客户端的 Last-Event-ID。
    if not ephemeral and event.get("seq") is not None:
        lines.append(f"id: {event['seq']}")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False, default=str)}")
    return "\n".join(lines) + "\n\n"


def _event_view(event: dict) -> dict:
    """把数据库事件转换为前端和 SSE 共用的公开事件格式。"""
    return {
        "event_id": event.get("event_id"),
        "seq": event.get("seq"),
        "type": event.get("type"),
        "timestamp": event.get("created_at"),
        "data": event.get("payload", {}),
        "ephemeral": False,
    }
