from sqlalchemy.ext.asyncio import AsyncSession

from app.application.tasks import TERMINAL_STATUSES, task_registry
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.models import elapsed_ms, utc_now
from app.infrastructure.persistence.repository import Repository


class WorkflowControlService:
    def __init__(self, session: AsyncSession):
        self.repository = Repository(session)

    async def cancel(self, run_id: str):
        run = await self.repository.get_run(run_id)
        if not run:
            raise ResourceNotFoundError("run", run_id)
        if run.status in TERMINAL_STATUSES:
            return run
        run.status = "cancelled"
        run.result_mode = "cancelled"
        run.completed_at = utc_now()
        run.duration_ms = elapsed_ms(run.started_at, run.completed_at)
        await self.repository.save_run(run)
        await self.repository.add_event(
            run_id=run.id,
            conversation_id=run.conversation_id,
            event_type="run.cancelled",
            stage=run.current_stage,
            data={"status": "cancelled", "runUrl": f"/api/v1/runs/{run.id}"},
        )
        task_registry.cancel(run.id)
        return run
