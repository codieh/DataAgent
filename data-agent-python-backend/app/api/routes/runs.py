"""运行（run）相关路由：创建、查询、取消、重试，以及 SSE 事件流订阅。

运行是分析任务的核心执行单元。创建即受理（202），实际执行异步进行，客户端通过
``/runs/{id}/events`` 的 Server-Sent Events 流实时接收进度。事件流支持基于
``after_seq`` / ``Last-Event-ID`` 的断线续传，并定期发送心跳保活。
"""

import asyncio

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import SessionDependency
from app.api.presenters import event_response, run_response
from app.api.schemas import AnalysisRunResponse, OperationResponse, RunAccepted, RunCreate
from app.application import RunViewService, TERMINAL_STATUSES, WorkflowControlService
from app.application.run_commands import RunCommandService
from app.application.executor import graph_runtime
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
        heartbeat_elapsed = 0.0
        while True:
            # 客户端断开立即结束生成器，释放服务端资源
            if await request.is_disconnected():
                return
            async with session_factory() as session:
                repository = Repository(session)
                events = await repository.list_events(run_id, sequence)
                run = await repository.get_run(run_id)
            for event in events:
                response = event_response(event)
                # 推进游标到本事件序号，确保不重复推送
                sequence = max(sequence, response.seq)
                if response.type in {"run.completed", "review.required"}:
                    event_name = "complete"
                elif response.type == "run.failed":
                    event_name = "error"
                else:
                    event_name = "message"
                yield format_sse(event_name, response.model_dump_json(by_alias=True), str(response.seq))
                heartbeat_elapsed = 0.0
            # 运行已终止且无新事件：正常结束流
            if run and run.status in TERMINAL_STATUSES and not events:
                return
            # 进入等待人工评审且无新事件：结束流，交由评审接口推进
            if run and run.status == "waiting_review" and not events:
                return
            # 无新事件时按轮询间隔休眠，累计到心跳阈值则发心跳保活
            await asyncio.sleep(settings.sse_poll_interval_seconds)
            heartbeat_elapsed += settings.sse_poll_interval_seconds
            if heartbeat_elapsed >= settings.sse_heartbeat_seconds:
                yield ": heartbeat\n\n"
                heartbeat_elapsed = 0.0

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        # 关闭代理缓冲，保证事件实时到达；禁用缓存
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
