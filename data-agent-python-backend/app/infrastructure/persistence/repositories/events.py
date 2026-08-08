"""运行事件仓储（Event repository）。

管理运行过程中的流式事件（``RunEventModel``）。核心约束是每条事件在所属运行内
拥有全局唯一且单调递增的事件序号 ``seq``，用于前端按序推送/增量拉取。

``seq`` 通过「对 AnalysisRunModel 执行 ``event_seq + 1`` 的原子 UPDATE 并返回」
来获取，避免并发追加时出现序号冲突（见 ``add_event``）。
"""

from typing import Any

from sqlalchemy import select, update

from app.infrastructure.persistence.models import AnalysisRunModel, RunEventModel
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class EventRepository(RepositoryBase):
    """运行事件聚合的仓储实现。"""

    async def add_event(
        self,
        *,
        run_id: str,
        conversation_id: str,
        event_type: str,
        stage: str | None,
        data: dict[str, Any],
    ) -> RunEventModel:
        """追加一条运行事件，并以原子方式分配全局递增的事件序号 ``seq``。

        通过对运行记录执行 ``event_seq = event_seq + 1`` 的 ``UPDATE ... RETURNING``
        获取新序号（数据库侧原子操作，天然规避并发竞争）；若运行不存在（返回 None）
        则抛 ``ValueError``。随后以该序号写入事件记录。
        """
        next_seq = await self.session.scalar(
            update(AnalysisRunModel)
            .where(AnalysisRunModel.id == run_id)
            .values(event_seq=AnalysisRunModel.event_seq + 1)
            .returning(AnalysisRunModel.event_seq)
        )
        if next_seq is None:
            raise ValueError(f"run not found: {run_id}")
        event = RunEventModel(
            id=new_id("evt"),
            conversation_id=conversation_id,
            run_id=run_id,
            seq=next_seq,
            type=event_type,
            stage=stage,
            data=data,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def list_events(self, run_id: str, after_seq: int = 0) -> list[RunEventModel]:
        """列出某运行下 ``seq`` 大于 ``after_seq`` 的事件（增量拉取），按序号升序。

        ``after_seq`` 缺省为 0，即返回全部；传入上次最大 ``seq`` 即可实现增量获取。
        """
        statement = (
            select(RunEventModel)
            .where(RunEventModel.run_id == run_id, RunEventModel.seq > after_seq)
            .order_by(RunEventModel.seq.asc())
        )
        return list((await self.session.scalars(statement)).all())

