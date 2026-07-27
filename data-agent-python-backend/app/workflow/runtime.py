"""分析工作流运行时（编排与生命周期管理）。

``GraphRuntime`` 负责装配所有基础设施依赖（数据库、LLM、检索器、数据集存储、
结果历史、Python 沙箱、记忆服务、上下文构建器等），构建并编译 LangGraph，
并对外提供：启动/关闭、流式执行（``stream``）、人工审核恢复（``resume``）、
读取当前状态（``state``）。检查点使用本地 SQLite 持久化，保证可中断恢复。
"""

from collections.abc import AsyncIterator
import asyncio
from contextlib import suppress
from datetime import timedelta
import logging
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from sqlalchemy import or_, and_, select
from sqlalchemy.engine import make_url

from app.config import Settings
from app.analysis import AnalysisDatasetStore, PythonAnalysisService, ResultHistoryService, create_python_sandbox
from app.infrastructure.datasource.sql import BusinessDatabase
from app.infrastructure.llm.openai import OpenAiChatClient
from app.memory import ContextBuilder, ConversationSummarizer, LongTermMemoryExtractor, MemoryProvider
from app.context.manager import AgentContextManager
from app.retrieval import KnowledgeRetriever
from app.workflow.graph import build_analysis_graph
from app.workflow.context_builder import AgentContextBuilder
from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.models import AnalysisRunModel, utc_now


logger = logging.getLogger(__name__)


class GraphRuntime:
    """LangGraph 分析工作流的运行时。

    在构造时装配依赖并创建各服务对象；在 ``startup`` 中建立检查点、编译图；
    ``shutdown`` 释放连接。线程粒度由调用方以 ``run_id`` 作为 thread_id 控制。
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = BusinessDatabase(settings)
        self.llm = OpenAiChatClient(settings)
        self.retriever = KnowledgeRetriever(settings)
        self.dataset_store = AnalysisDatasetStore(settings)
        self.result_history = ResultHistoryService(settings, self.dataset_store)
        self.agent_context_manager = AgentContextManager(settings, self.llm)
        self.agent_context_builder = AgentContextBuilder(
            settings,
            self.result_history,
            self.agent_context_manager,
        )
        self.python_sandbox = create_python_sandbox(settings)
        self.python_analysis = PythonAnalysisService(settings, self.llm, self.python_sandbox)
        self.memory_provider = MemoryProvider(settings)
        self.conversation_summarizer = ConversationSummarizer(settings, self.llm)
        self.context_builder = ContextBuilder(settings, self.memory_provider, self.conversation_summarizer)
        self.memory_extractor = LongTermMemoryExtractor(settings, self.llm, self.memory_provider)
        self._checkpointer_context = None
        self._checkpointer = None
        self._checkpoint_cleanup_task: asyncio.Task[None] | None = None
        self.graph = None

    async def startup(self) -> None:
        """初始化运行时：清理过期数据集、建立 SQLite 检查点并编译 LangGraph。"""
        expired_datasets = await self.dataset_store.cleanup()
        orphaned_files = await self.dataset_store.cleanup_orphans()
        logger.info(
            "dataset startup cleanup completed: expired=%d orphanedFiles=%d",
            expired_datasets,
            orphaned_files,
        )
        # 检查点目录与业务库同目录：若未配置或内存库，则回退到 ./data/app.db
        database_path = make_url(self.settings.database_url).database
        if not database_path or database_path == ":memory:":
            database_path = str(Path.cwd() / "data" / "app.db")
        checkpoint_path = Path(database_path).with_name("checkpoints.db")
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpointer_context = AsyncSqliteSaver.from_conn_string(str(checkpoint_path))
        # 进入异步上下文，获得可复用的检查点 saver
        self._checkpointer = await self._checkpointer_context.__aenter__()
        cleanup_stats = await self.cleanup_terminal_checkpoints()
        logger.info("checkpoint startup cleanup completed: %s", cleanup_stats)
        # 装配节点并编译图，绑定检查点以支持中断/恢复
        self.graph = build_analysis_graph(
            self.llm,
            self.database,
            self.retriever,
            self.python_analysis,
            self.dataset_store,
            self.result_history,
            self.agent_context_builder,
        ).compile(checkpointer=self._checkpointer)
        self._checkpoint_cleanup_task = asyncio.create_task(
            self._checkpoint_cleanup_loop(), name="checkpoint-cleanup"
        )

    async def shutdown(self) -> None:
        """释放资源：关闭数据库连接、LLM（可选）与检查点上下文，并将图置空。"""
        if self._checkpoint_cleanup_task is not None:
            self._checkpoint_cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._checkpoint_cleanup_task
            self._checkpoint_cleanup_task = None
        await self.database.close()
        close_llm = getattr(self.llm, "close", None)
        if close_llm is not None:
            await close_llm()
        if self._checkpointer_context is not None:
            await self._checkpointer_context.__aexit__(None, None, None)
        self.graph = None

    async def stream(self, run_id: str, state: dict[str, Any]) -> AsyncIterator[tuple[str, Any]]:
        """以 ``run_id`` 作为 thread_id 流式执行工作流，逐块产出（custom/updates）。"""
        if self.graph is None:
            raise RuntimeError("LangGraph runtime is not started")
        config = {"configurable": {"thread_id": run_id}}
        async for item in self.graph.astream(state, config=config, stream_mode=["custom", "updates"]):
            yield item

    async def resume(self, run_id: str, approved: bool, comment: str) -> AsyncIterator[tuple[str, Any]]:
        """在人工审核中断后恢复执行：把审批结果作为 Command.resume 回灌到图。"""
        if self.graph is None:
            raise RuntimeError("LangGraph runtime is not started")
        config = {"configurable": {"thread_id": run_id}}
        command = Command(resume={"approved": approved, "comment": comment})
        async for item in self.graph.astream(command, config=config, stream_mode=["custom", "updates"]):
            yield item

    async def can_resume_failed(self, run_id: str) -> bool:
        """判断失败 Run 是否仍有可继续执行的 checkpoint 和待执行节点。"""
        if self.graph is None:
            raise RuntimeError("LangGraph runtime is not started")
        snapshot = await self.graph.aget_state({"configurable": {"thread_id": run_id}})
        return bool(snapshot.values) and bool(snapshot.next)

    async def retry_failed(self, run_id: str) -> AsyncIterator[tuple[str, Any]]:
        """从失败节点之前的 checkpoint 原地续跑，不重放已完成节点。"""
        if self.graph is None:
            raise RuntimeError("LangGraph runtime is not started")
        config = {"configurable": {"thread_id": run_id}}
        # None 表示不注入新输入，直接继续 checkpoint 中尚未完成的任务。
        async for item in self.graph.astream(
            None,
            config=config,
            stream_mode=["custom", "updates"],
        ):
            yield item

    async def state(self, run_id: str) -> dict[str, Any]:
        """读取某次运行（thread_id）的当前图状态快照。"""
        if self.graph is None:
            raise RuntimeError("LangGraph runtime is not started")
        snapshot = await self.graph.aget_state({"configurable": {"thread_id": run_id}})
        return dict(snapshot.values)

    async def delete_checkpoints(self, run_ids: list[str]) -> int:
        """删除指定 Run 的全部 LangGraph checkpoint 与 pending writes。"""
        if self._checkpointer is None:
            raise RuntimeError("LangGraph checkpointer 尚未启动")
        unique_run_ids = list(dict.fromkeys(run_ids))
        for run_id in unique_run_ids:
            await self._checkpointer.adelete_thread(run_id)
        return len(unique_run_ids)

    async def cleanup_terminal_checkpoints(self) -> dict[str, int]:
        """清理完成/取消、过期失败以及已无 Run 记录的 checkpoint。"""
        if self._checkpointer is None:
            raise RuntimeError("LangGraph checkpointer 尚未启动")
        failed_cutoff = utc_now() - timedelta(hours=self.settings.checkpoint_failed_ttl_hours)
        async with session_factory() as session:
            known_run_ids = set((await session.scalars(select(AnalysisRunModel.id))).all())
            terminal_ids = set(
                (
                    await session.scalars(
                        select(AnalysisRunModel.id).where(
                            or_(
                                AnalysisRunModel.status.in_(["completed", "cancelled"]),
                                and_(
                                    AnalysisRunModel.status == "failed",
                                    AnalysisRunModel.completed_at.is_not(None),
                                    AnalysisRunModel.completed_at <= failed_cutoff,
                                ),
                            )
                        )
                    )
                ).all()
            )
        checkpoint_run_ids: set[str] = set()
        async for checkpoint in self._checkpointer.alist(None):
            thread_id = checkpoint.config.get("configurable", {}).get("thread_id")
            if thread_id:
                checkpoint_run_ids.add(str(thread_id))
        orphan_ids = checkpoint_run_ids - known_run_ids
        targets = sorted((terminal_ids & checkpoint_run_ids) | orphan_ids)
        await self.delete_checkpoints(targets)
        return {
            "deletedThreads": len(targets),
            "terminalThreads": len(terminal_ids & checkpoint_run_ids),
            "orphanThreads": len(orphan_ids),
        }

    async def _checkpoint_cleanup_loop(self) -> None:
        """运行期间定时回收超过保留期的失败 checkpoint。"""
        while True:
            await asyncio.sleep(self.settings.checkpoint_cleanup_interval_seconds)
            try:
                stats = await self.cleanup_terminal_checkpoints()
                logger.info("checkpoint periodic cleanup completed: %s", stats)
            except Exception:
                logger.exception("checkpoint periodic cleanup failed")
