"""结果历史服务。

提供「会话维度」的持久化 SQL 结果检索能力：最近结果列表、关键字搜索、
以及针对单个数据集的分页查看（读取全量数据）。所有数据访问均限定在单个会话内，
是前端「历史结果」面板的后端支撑。
"""

from typing import Any

from app.analysis.datasets import AnalysisDatasetStore
from app.config import Settings
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.repository import Repository


class ResultHistoryService:
    """Conversation-scoped access to durable SQL result artifacts."""

    def __init__(self, settings: Settings, dataset_store: AnalysisDatasetStore | None = None):
        self.settings = settings
        # 允许注入 dataset_store，便于测试或复用既有实例
        self.dataset_store = dataset_store or AnalysisDatasetStore(settings)

    async def recent(self, conversation_id: str, limit: int) -> list[dict[str, Any]]:
        """返回会话最近的若干条结果集（limit 夹在 1~10）。"""
        async with session_factory() as session:
            # 限制最大返回 10 条，避免前端一次拉取过多
            items = await Repository(session).list_conversation_results(conversation_id, min(max(limit, 1), 10))
            return [_catalog_item(run, query, result) for run, query, result in items]

    async def search(self, conversation_id: str, query: str, scope: str, limit: int) -> list[dict[str, Any]]:
        """在会话内搜索结果集。

        优先走全文检索（FTS）；FTS 无命中时退化为普通模糊匹配。
        ``scope`` 当前保留用于后续扩展（如限定字段范围）。
        """
        async with session_factory() as session:
            repository = Repository(session)
            fts_matches = await repository.search_result_history_fts(
                conversation_id, query, min(max(limit, 1), 10)
            )
            # FTS 命中时，用命中记录补充行数、创建时间等元信息
            if fts_matches:
                results = []
                for match in fts_matches:
                    result = await repository.get_conversation_result_set(
                        conversation_id, match["datasetId"]
                    )
                    if result is not None:
                        results.append(
                            {
                                **match,
                                "rowCount": result.total_rows,
                                "createdAt": result.created_at.isoformat(),
                            }
                        )
                return results
            # FTS 未命中：退化为基于 repository 的关键字检索
            items = await repository.search_conversation_results(
                conversation_id, query, min(max(limit, 1), 10)
            )
            return [_catalog_item(run, query_model, result) for run, query_model, result in items]

    async def inspect(
        self, conversation_id: str, dataset_id: str, offset: int, limit: int
    ) -> dict[str, Any]:
        """分页查看单个数据集的全量内容。

        参数：
            offset/limit：分页参数（offset 下限 0，limit 上限 50）。
        返回：包含列、当前页行、总行数、是否还有更多等信息的字典。
        异常：找不到对应数据集时抛出 ResourceNotFoundError。
        """
        async with session_factory() as session:
            result = await Repository(session).get_conversation_result_set(conversation_id, dataset_id)
            if result is None:
                raise ResourceNotFoundError("result_set", dataset_id)
            # 借助数据集存储按页读取（可能来自 CSV 全量或 SQLite 预览）
            rows = await self.dataset_store.read_rows(
                result, offset=max(0, offset), limit=min(max(limit, 1), 50)
            )
            return {
                "datasetId": result.id,
                "columns": result.columns,
                "rows": rows,
                "rowCount": result.total_rows,
                "offset": max(0, offset),
                "returnedRows": len(rows),
                # 当前页结束位置是否未到总行数，决定是否还有下一页
                "hasMore": max(0, offset) + len(rows) < result.total_rows,
                "truncated": result.truncated,
            }


def _catalog_item(run, query, result) -> dict[str, Any]:
    """把运行/查询/结果集三元组规整为前端目录卡片所需的精简结构。"""
    return {
        "datasetId": result.id,
        # 优先展示经上下文改写后的问题，否则回退原始问题
        "question": run.contextualized_question or run.question,
        "sql": query.sql,
        "columns": [item.get("name") for item in result.columns],
        "rowCount": result.total_rows,
        "createdAt": result.created_at.isoformat(),
    }
