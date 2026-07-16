"""运行控制服务：对进行中的分析运行执行可中断的控制操作。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.tasks import TERMINAL_STATUSES, task_registry
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.models import elapsed_ms, utc_now
from app.infrastructure.persistence.repository import Repository


class WorkflowControlService:
    """工作流控制服务：目前提供取消运行的能力。"""

    def __init__(self, session: AsyncSession):
        self.repository = Repository(session)

    async def cancel(self, run_id: str):
        """取消一个分析运行。

        参数:
            run_id: 目标运行 ID（不存在则抛 ResourceNotFoundError）。
        返回:
            取消后的运行记录。若运行已是终态则直接返回，幂等。
        副作用:
            将运行标记为 cancelled 并结算耗时、广播取消事件，同时取消后台任务。
        """
        run = await self.repository.get_run(run_id)
        if not run:
            raise ResourceNotFoundError("run", run_id)
        # 终态运行不可再取消，直接返回当前记录。
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
        # 等待后台任务真正结束，避免返回后 LangGraph 继续写入 checkpoint。
        await task_registry.cancel_and_wait(run.id)
        return run
