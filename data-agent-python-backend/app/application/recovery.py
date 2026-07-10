"""应用重启后的运行补偿。

当进程被重启（如部署/崩溃）时，原本在内存中由 asyncio 后台任务驱动的分析运行
会随进程一起消失，但数据库中可能仍残留 `queued` / `running` 状态的记录。本模块
在服务启动时调用，把这些「悬挂」的运行显式标记为失败，使状态机回到终态，
避免前端永远停留在「运行中」。
"""

from sqlalchemy import select

from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.models import AnalysisRunModel, utc_now
from app.infrastructure.persistence.repository import Repository


async def recover_interrupted_runs() -> None:
    """应用重启后，把残留的 queued/running 本地任务显式标记为失败。"""
    async with session_factory() as session:
        repository = Repository(session)
        # 取出所有尚未到达终态的运行（queued 尚未派发、running 正在执行）。
        result = await session.scalars(
            select(AnalysisRunModel).where(AnalysisRunModel.status.in_(["queued", "running"]))
        )
        for run in result.all():
            # 由于驱动任务已随进程退出而消失，无法继续，统一转为失败并提示用户重试。
            run.status = "failed"
            run.result_mode = "service_restarted"
            run.error_code = "service_restarted"
            run.error_message = "服务重启导致本次本地任务中断，请重新执行。"
            run.completed_at = utc_now()
            await repository.save_run(run)

