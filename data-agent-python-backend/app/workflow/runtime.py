from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from sqlalchemy.engine import make_url

from app.config import Settings
from app.infrastructure.datasource.sql import BusinessDatabase
from app.infrastructure.llm.openai import OpenAiChatClient
from app.retrieval import KnowledgeRetriever
from app.workflow.graph import build_analysis_graph


class GraphRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = BusinessDatabase(settings)
        self.llm = OpenAiChatClient(settings)
        self.retriever = KnowledgeRetriever(settings)
        self._checkpointer_context = None
        self._checkpointer = None
        self.graph = None

    async def startup(self) -> None:
        database_path = make_url(self.settings.database_url).database
        if not database_path or database_path == ":memory:":
            database_path = str(Path.cwd() / "data" / "app.db")
        checkpoint_path = Path(database_path).with_name("checkpoints.db")
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpointer_context = AsyncSqliteSaver.from_conn_string(str(checkpoint_path))
        self._checkpointer = await self._checkpointer_context.__aenter__()
        self.graph = build_analysis_graph(self.llm, self.database, self.retriever).compile(checkpointer=self._checkpointer)

    async def shutdown(self) -> None:
        await self.database.close()
        close_llm = getattr(self.llm, "close", None)
        if close_llm is not None:
            await close_llm()
        if self._checkpointer_context is not None:
            await self._checkpointer_context.__aexit__(None, None, None)
        self.graph = None

    async def stream(self, run_id: str, state: dict[str, Any]) -> AsyncIterator[tuple[str, Any]]:
        if self.graph is None:
            raise RuntimeError("LangGraph runtime is not started")
        config = {"configurable": {"thread_id": run_id}}
        async for item in self.graph.astream(state, config=config, stream_mode=["custom", "updates"]):
            yield item

    async def resume(self, run_id: str, approved: bool, comment: str) -> AsyncIterator[tuple[str, Any]]:
        if self.graph is None:
            raise RuntimeError("LangGraph runtime is not started")
        config = {"configurable": {"thread_id": run_id}}
        command = Command(resume={"approved": approved, "comment": comment})
        async for item in self.graph.astream(command, config=config, stream_mode=["custom", "updates"]):
            yield item

    async def state(self, run_id: str) -> dict[str, Any]:
        if self.graph is None:
            raise RuntimeError("LangGraph runtime is not started")
        snapshot = await self.graph.aget_state({"configurable": {"thread_id": run_id}})
        return dict(snapshot.values)
