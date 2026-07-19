"""运行（run）相关路由：创建、查询、取消、重试，以及 SSE 事件流订阅。

运行是分析任务的核心执行单元。创建即受理（202），实际执行异步进行，客户端通过
``/runs/{id}/events`` 的 Server-Sent Events 流实时接收进度。事件流支持基于
``after_seq`` / ``Last-Event-ID`` 的断线续传，并定期发送心跳保活。
"""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import SessionDependency
from app.api.presenters import event_response, run_response
from app.api.schemas import AnalysisRunResponse, OperationResponse, RunAccepted, RunCreate
from app.application import RunViewService, TERMINAL_STATUSES, WorkflowControlService
from app.application.run_commands import RunCommandService
from app.application.executor import graph_runtime
from app.application.live_events import run_live_event_broker
from app.config import get_settings
from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.repository import Repository


router = APIRouter(tags=["runs"])


def accepted(run) -> RunAccepted:
    """构造「运行已受理」响应，并附带事件流订阅地址。"""
    return RunAccepted(
        run_id=run.id,
        conversation_id=run.conversation_id,
        status=run.status,
        events_url=f"/api/v1/runs/{run.id}/events",
    )


@router.post(
    "/conversations/{conversation_id}/runs",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(conversation_id: str, body: RunCreate, session: SessionDependency) -> RunAccepted:
    # 仅创建并受理运行，真正的分析流程在后台异步推进
    run = await RunCommandService(Repository(session)).create(
        conversation_id=conversation_id,
        query=body.query,
        human_review_enabled=body.human_review_enabled,
        idempotency_key=body.idempotency_key,
        agent_id=body.agent_id,
        datasource_id=body.datasource_id,
    )
    return accepted(run)


@router.get("/runs/{run_id}", response_model=AnalysisRunResponse)
async def get_run(run_id: str, session: SessionDependency) -> AnalysisRunResponse:
    # 返回运行完整详情（聚合阶段/查询/分析/评审等）
    return run_response(await RunViewService(session).build(run_id))


@router.post("/runs/{run_id}/cancel", response_model=OperationResponse)
async def cancel_run(run_id: str, session: SessionDependency) -> OperationResponse:
    run = await WorkflowControlService(session).cancel(run_id)
    # 取消成功状态为 cancelled，否则表示任务已经结束无法取消
    message = "任务已取消" if run.status == "cancelled" else "任务已经结束"
    if run.status == "cancelled":
        await graph_runtime.delete_checkpoints([run.id])
    return OperationResponse(ok=True, status=run.status, message=message)


@router.post("/runs/{run_id}/retry", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def retry_run(run_id: str, session: SessionDependency) -> RunAccepted:
    return accepted(await RunCommandService(Repository(session)).retry(run_id))


def format_sse(event_type: str, data: str, event_id: str | None = None) -> str:
    """把事件渲染为标准 SSE 文本帧（多行 data 需逐行展开）。"""
    lines = [f"event: {event_type}"]
    if event_id:
        lines.append(f"id: {event_id}")
    lines.extend(f"data: {line}" for line in data.splitlines() or [""])
    return "\n".join(lines) + "\n\n"


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    after_seq: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    settings = get_settings()
    # 先确认运行存在，避免为无效 ID 建立空流
    async with session_factory() as session:
        run = await Repository(session).get_run(run_id)
        if not run:
            from app.domain.errors import ResourceNotFoundError

            raise ResourceNotFoundError("run", run_id)

    try:
        # 优先用显式 after_seq，否则用浏览器自动重连携带的 Last-Event-ID 续传
        resume_sequence = after_seq if after_seq is not None else int(last_event_id or 0)
    except ValueError:
        resume_sequence = 0

    async def event_stream():
        sequence = resume_sequence
        async with run_live_event_broker.subscribe(run_id) as subscription:
            # 订阅必须早于数据库补发，期间产生的持久事件会同时出现在两处，依靠 seq 去重。
            async with session_factory() as session:
                repository = Repository(session)
                events = await repository.list_events(run_id, sequence)
                current_run = await repository.get_run(run_id)
            for event in events:
                response = event_response(event)
                if response.seq is None:
                    raise RuntimeError(f"持久事件缺少 seq: eventId={response.event_id}")
                sequence = max(sequence, response.seq)
                yield _persistent_sse(response)
            if current_run and (
                current_run.status in TERMINAL_STATUSES or current_run.status == "waiting_review"
            ):
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    live = await asyncio.wait_for(
                        subscription.queue.get(), timeout=settings.sse_heartbeat_seconds
                    )
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if live.get("kind") == "overflow":
                    # 让客户端明确重连；Last-Event-ID 会补回持久事件，最终快照补回 Summary。
                    error = {
                        "eventId": f"live-{run_id}-{uuid4().hex}",
                        "conversationId": run.conversation_id,
                        "runId": run_id,
                        "seq": None,
                        "type": "stream.overflow",
                        "stage": None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {
                            "code": "sse_consumer_too_slow",
                            "message": "事件消费速度过慢，请重新连接事件流。",
                        },
                    }
                    yield format_sse("error", json.dumps(error, ensure_ascii=False))
                    return
                if live.get("kind") == "persistent":
                    event_seq = int(live["seq"])
                    if event_seq <= sequence:
                        continue
                    sequence = event_seq
                    yield _persistent_payload_sse(live)
                    if live["type"] in {"run.completed", "run.failed", "run.cancelled", "review.required"}:
                        return
                else:
                    payload = {
                        "eventId": live["eventId"],
                        "conversationId": run.conversation_id,
                        "runId": run_id,
                        "seq": None,
                        "type": live["type"],
                        "stage": live.get("stage"),
                        "timestamp": live["timestamp"],
                        "data": live.get("data", {}),
                    }
                    yield format_sse("message", json.dumps(payload, ensure_ascii=False))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        # 关闭代理缓冲，保证事件实时到达；禁用缓存
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _event_name(event_type: str) -> str:
    if event_type in {"run.completed", "review.required"}:
        return "complete"
    if event_type in {"run.failed", "run.cancelled"}:
        return "error"
    return "message"


def _persistent_sse(response) -> str:
    return format_sse(
        _event_name(response.type),
        response.model_dump_json(by_alias=True),
        str(response.seq),
    )


def _persistent_payload_sse(payload: dict) -> str:
    data = {key: value for key, value in payload.items() if key != "kind"}
    return format_sse(
        _event_name(str(payload["type"])),
        json.dumps(data, ensure_ascii=False),
        str(payload["seq"]),
    )
