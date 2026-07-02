from typing import Any

from sqlalchemy import select, update

from app.infrastructure.persistence.models import AnalysisRunModel, RunEventModel
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class EventRepository(RepositoryBase):
    async def add_event(
        self,
        *,
        run_id: str,
        conversation_id: str,
        event_type: str,
        stage: str | None,
        data: dict[str, Any],
    ) -> RunEventModel:
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
        statement = (
            select(RunEventModel)
            .where(RunEventModel.run_id == run_id, RunEventModel.seq > after_seq)
            .order_by(RunEventModel.seq.asc())
        )
        return list((await self.session.scalars(statement)).all())

