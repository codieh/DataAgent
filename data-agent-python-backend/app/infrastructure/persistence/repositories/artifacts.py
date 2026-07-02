from typing import Any

from sqlalchemy import select

from app.infrastructure.persistence.models import ArtifactModel, QueryModel, ResultSetModel
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class ArtifactRepository(RepositoryBase):
    async def add_artifact(
        self,
        *,
        run_id: str,
        stage: str,
        artifact_type: str,
        summary: str,
        payload: dict[str, Any],
    ) -> ArtifactModel:
        artifact = ArtifactModel(
            id=new_id("artifact"),
            run_id=run_id,
            stage=stage,
            type=artifact_type,
            summary=summary,
            payload=payload,
        )
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def get_artifact(self, artifact_id: str) -> ArtifactModel | None:
        return await self.session.get(ArtifactModel, artifact_id)

    async def list_artifacts(self, run_id: str) -> list[ArtifactModel]:
        statement = select(ArtifactModel).where(ArtifactModel.run_id == run_id).order_by(ArtifactModel.created_at.asc())
        return list((await self.session.scalars(statement)).all())

    async def add_query(self, **values: Any) -> QueryModel:
        query = QueryModel(id=new_id("query"), **values)
        self.session.add(query)
        await self.session.commit()
        await self.session.refresh(query)
        return query

    async def list_queries(self, run_id: str) -> list[QueryModel]:
        statement = select(QueryModel).where(QueryModel.run_id == run_id).order_by(QueryModel.created_at.asc())
        return list((await self.session.scalars(statement)).all())

    async def add_result_set(
        self, *, run_id: str, columns: list[dict[str, Any]], rows: list[dict[str, Any]]
    ) -> ResultSetModel:
        result_set = ResultSetModel(
            id=new_id("result"), run_id=run_id, columns=columns, rows=rows, total_rows=len(rows)
        )
        self.session.add(result_set)
        await self.session.commit()
        await self.session.refresh(result_set)
        return result_set

    async def get_result_set(self, result_set_id: str) -> ResultSetModel | None:
        return await self.session.get(ResultSetModel, result_set_id)

