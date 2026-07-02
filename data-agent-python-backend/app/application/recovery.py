from sqlalchemy import select

from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.models import AnalysisRunModel, utc_now
from app.infrastructure.persistence.repository import Repository


async def recover_interrupted_runs() -> None:
    """Make interrupted local tasks explicit after an application restart."""
    async with session_factory() as session:
        repository = Repository(session)
        result = await session.scalars(
            select(AnalysisRunModel).where(AnalysisRunModel.status.in_(["queued", "running"]))
        )
        for run in result.all():
            run.status = "failed"
            run.result_mode = "service_restarted"
            run.error_code = "service_restarted"
            run.error_message = "服务重启导致本次本地任务中断，请重新执行。"
            run.completed_at = utc_now()
            await repository.save_run(run)

