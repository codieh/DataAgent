"""产物与查询结果仓储（Artifact repository）。

涵盖产物（Artifact）、SQL 查询（Query）、结果集（ResultSet）三类实体的持久化，
以及两类「历史结果」检索能力：

- 关系型检索（``list_conversation_results``/``search_conversation_results``）：基于
  普通 SQL 的 JOIN 查询，按对话维度列出或模糊匹配问题与 SQL。
- 全文检索（``index_result_history``/``search_result_history_fts``）：维护并查询
  SQLite 的 ``result_history_fts`` 虚拟表，支持 trigram 分词的模糊搜索。

注意：全文检索方法依赖 SQLite + FTS5，非 SQLite 后端不会创建该虚拟表，调用
前需确保数据库已初始化（见 ``database.initialize_database``）。
"""

from typing import Any

from sqlalchemy import or_, select, text

from app.infrastructure.persistence.models import AnalysisRunModel, ArtifactModel, QueryModel, ResultSetModel
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class ArtifactRepository(RepositoryBase):
    """产物/查询/结果集聚合的仓储实现。"""

    async def add_artifact(
        self,
        *,
        run_id: str,
        stage: str,
        artifact_type: str,
        summary: str,
        payload: dict[str, Any],
    ) -> ArtifactModel:
        """新增一条产物记录（如图表配置、可视化 JSON 等）。"""
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
        """按 ID 获取产物。"""
        return await self.session.get(ArtifactModel, artifact_id)

    async def list_artifacts(self, run_id: str) -> list[ArtifactModel]:
        """列出某运行下的全部产物，按创建时间升序。"""
        statement = select(ArtifactModel).where(ArtifactModel.run_id == run_id).order_by(ArtifactModel.created_at.asc())
        return list((await self.session.scalars(statement)).all())

    async def add_query(self, **values: Any) -> QueryModel:
        """新增一条 SQL 查询记录，参数以关键字形式透传（``**values``）。"""
        query = QueryModel(id=new_id("query"), **values)
        self.session.add(query)
        await self.session.commit()
        await self.session.refresh(query)
        return query

    async def list_queries(self, run_id: str) -> list[QueryModel]:
        """列出某运行下的全部查询记录，按创建时间升序。"""
        statement = select(QueryModel).where(QueryModel.run_id == run_id).order_by(QueryModel.created_at.asc())
        return list((await self.session.scalars(statement)).all())

    async def add_result_set(
        self,
        *,
        run_id: str,
        columns: list[dict[str, Any]],
        rows: list[dict[str, Any]],
        total_rows: int | None = None,
        truncated: bool = False,
        storage_type: str = "sqlite",
        file_path: str | None = None,
        expires_at=None,
    ) -> ResultSetModel:
        """新增一个结果集；``total_rows`` 缺省时取实际行数。"""
        result_set = ResultSetModel(
            id=new_id("result"),
            run_id=run_id,
            columns=columns,
            rows=rows,
            # 未显式提供总行数时以当前已存行数为准（可能小于未截断的真实总数）
            total_rows=len(rows) if total_rows is None else total_rows,
            truncated=truncated,
            storage_type=storage_type,
            file_path=file_path,
            expires_at=expires_at,
        )
        self.session.add(result_set)
        await self.session.commit()
        await self.session.refresh(result_set)
        return result_set

    async def get_result_set(self, result_set_id: str) -> ResultSetModel | None:
        """按 ID 获取结果集。"""
        return await self.session.get(ResultSetModel, result_set_id)

    async def get_conversation_result_set(
        self, conversation_id: str, result_set_id: str
    ) -> ResultSetModel | None:
        """按结果集 ID 获取，但要求该结果集所属运行属于指定对话（越权访问返回 None）。"""
        statement = (
            select(ResultSetModel)
            .join(AnalysisRunModel, AnalysisRunModel.id == ResultSetModel.run_id)
            .where(
                ResultSetModel.id == result_set_id,
                AnalysisRunModel.conversation_id == conversation_id,
            )
        )
        return await self.session.scalar(statement)

    async def list_conversation_result_sets(self, conversation_id: str) -> list[ResultSetModel]:
        """列出会话下全部结果集，供删除会话前收集外部文件引用。"""
        statement = (
            select(ResultSetModel)
            .join(AnalysisRunModel, AnalysisRunModel.id == ResultSetModel.run_id)
            .where(AnalysisRunModel.conversation_id == conversation_id)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_conversation_results(self, conversation_id: str, limit: int):
        """列出某对话关联的结果集（经运行、查询 JOIN），按结果集创建时间倒序。"""
        statement = (
            select(AnalysisRunModel, QueryModel, ResultSetModel)
            .join(QueryModel, QueryModel.run_id == AnalysisRunModel.id)
            .join(ResultSetModel, ResultSetModel.id == QueryModel.result_set_id)
            .where(AnalysisRunModel.conversation_id == conversation_id)
            .order_by(ResultSetModel.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(statement)).all())

    async def search_conversation_results(self, conversation_id: str, query: str, limit: int):
        """按关键词模糊搜索某对话的问题与 SQL；空查询则回退为列出全部。"""
        terms = [term for term in query.strip().split() if term]
        statement = (
            select(AnalysisRunModel, QueryModel, ResultSetModel)
            .join(QueryModel, QueryModel.run_id == AnalysisRunModel.id)
            .join(ResultSetModel, ResultSetModel.id == QueryModel.result_set_id)
            .where(AnalysisRunModel.conversation_id == conversation_id)
        )
        # 每个词在 question 或 sql 上做模糊匹配，多个词为「或」关系
        if terms:
            statement = statement.where(
                or_(*[or_(AnalysisRunModel.question.ilike(f"%{term}%"), QueryModel.sql.ilike(f"%{term}%")) for term in terms])
            )
        statement = statement.order_by(ResultSetModel.created_at.desc()).limit(limit)
        return list((await self.session.execute(statement)).all())

    async def index_result_history(
        self,
        conversation_id: str,
        run_id: str,
        dataset_id: str,
        question: str,
        sql: str,
        columns: list[str],
        summary: str = "",
    ) -> None:
        """将一次分析结果写入 ``result_history_fts`` 全文索引（同 dataset_id 先删后插）。

        写入前按 ``dataset_id`` 删除旧索引（保证同一数据集只保留最新一份）；
        ``columns`` 以空格拼接成可分词文本；“更新后提交。
        """
        await self.session.execute(
            text("DELETE FROM result_history_fts WHERE dataset_id = :dataset_id"),
            {"dataset_id": dataset_id},
        )
        await self.session.execute(
            text("""INSERT INTO result_history_fts
            (dataset_id, conversation_id, run_id, question, sql, columns, summary)
            VALUES (:dataset_id, :conversation_id, :run_id, :question, :sql, :columns, :summary)"""),
            {
                "dataset_id": dataset_id,
                "conversation_id": conversation_id,
                "run_id": run_id,
                "question": question,
                "sql": sql,
                # 列名拼接为单段文本，便于 trigram 分词检索
                "columns": " ".join(columns),
                "summary": summary,
            },
        )
        await self.session.commit()

    async def search_result_history_fts(
        self, conversation_id: str, query: str, limit: int
    ) -> list[dict[str, Any]]:
        """在结果历史全文索引中搜索；仅收录长度 >= 3 的词条，多词以 AND 组合。

        返回 ``[{datasetId, runId, question, sql, columns}, ...]``，``columns`` 由空格
        切分还原为列表；无有效词条时直接返回空列表（避免无意义查询）。
        """
        terms = [term.replace('"', "") for term in query.split() if len(term.replace('"', "")) >= 3]
        if not terms:
            return []
        # 多词均被双引号包裹并以 AND 连接，要求全部命中（trigram 分词）
        expression = " AND ".join(f'"{term}"' for term in terms)
        rows = await self.session.execute(
            text("""SELECT dataset_id, run_id, question, sql, columns
            FROM result_history_fts
            WHERE result_history_fts MATCH :query AND conversation_id = :conversation_id
            ORDER BY rank LIMIT :limit"""),
            {"query": expression, "conversation_id": conversation_id, "limit": limit},
        )
        return [
            {"datasetId": row.dataset_id, "runId": row.run_id, "question": row.question,
             "sql": row.sql, "columns": row.columns.split()}
            for row in rows
        ]
