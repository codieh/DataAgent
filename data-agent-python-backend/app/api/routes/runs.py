import asyncio

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import SessionDependency
from app.api.presenters import event_response, run_response
from app.api.schemas import AnalysisRunResponse, OperationResponse, RunAccepted, RunCreate
from app.application import RunViewService, TERMINAL_STATUSES, WorkflowControlService
from app.application.run_commands import RunCommandService
from app.config import get_settings
from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.repository import Repository


router = APIRouter(tags=["runs"])


def accepted(run) -> RunAccepted:
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
    return run_response(await RunViewService(session).build(run_id))


@router.post("/runs/{run_id}/cancel", response_model=OperationResponse)
async def cancel_run(run_id: str, session: SessionDependency) -> OperationResponse:
    run = await WorkflowControlService(session).cancel(run_id)
    message = "任务已取消" if run.status == "cancelled" else "任务已经结束"
    return OperationResponse(ok=True, status=run.status, message=message)


@router.post("/runs/{run_id}/retry", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def retry_run(run_id: str, session: SessionDependency) -> RunAccepted:
    return accepted(await RunCommandService(Repository(session)).retry(run_id))


def format_sse(event_type: str, data: str, event_id: str | None = None) -> str:
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
    async with session_factory() as session:
        run = await Repository(session).get_run(run_id)
        if not run:
            from app.domain.errors import ResourceNotFoundError

            raise ResourceNotFoundError("run", run_id)

    try:
        resume_sequence = after_seq if after_seq is not None else int(last_event_id or 0)
    except ValueError:
        resume_sequence = 0

    async def event_stream():
        sequence = resume_sequence
        heartbeat_elapsed = 0.0
        while True:
            if await request.is_disconnected():
                return
            async with session_factory() as session:
                repository = Repository(session)
                events = await repository.list_events(run_id, sequence)
                run = await repository.get_run(run_id)
            for event in events:
                response = event_response(event)
                sequence = max(sequence, response.seq)
                if response.type in {"run.completed", "review.required"}:
                    event_name = "complete"
                elif response.type == "run.failed":
                    event_name = "error"
                else:
                    event_name = "message"
                yield format_sse(event_name, response.model_dump_json(by_alias=True), str(response.seq))
                heartbeat_elapsed = 0.0
            if run and run.status in TERMINAL_STATUSES and not events:
                return
            if run and run.status == "waiting_review" and not events:
                return
            await asyncio.sleep(settings.sse_poll_interval_seconds)
            heartbeat_elapsed += settings.sse_poll_interval_seconds
            if heartbeat_elapsed >= settings.sse_heartbeat_seconds:
                yield ": heartbeat\n\n"
                heartbeat_elapsed = 0.0

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
