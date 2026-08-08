"""基于 LangChain ``create_agent`` 的数据分析 Agent 定义。"""

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from app.infrastructure.datasource.sql import BusinessDatabase
from app.retrieval import KnowledgeRetriever
from app.workflow.nodes.analysis import AnalysisNodes
from app.workflow.state import AnalysisState
from app.workflow.ports import LlmClient
from app.workflow.chat_model import LangChainChatModelAdapter
from app.workflow.middleware import DataAgentMiddleware
from app.workflow.prompts import AGENT_SYSTEM
from app.analysis.service import PythonAnalysisService
from app.analysis.datasets import AnalysisDatasetStore
from app.analysis.history import ResultHistoryService
from app.workflow.context_builder import AgentContextBuilder


def build_analysis_graph(
    llm: LlmClient,
    database: BusinessDatabase,
    retriever: KnowledgeRetriever,
    python_analysis: PythonAnalysisService | None = None,
    dataset_store: AnalysisDatasetStore | None = None,
    result_history: ResultHistoryService | None = None,
    agent_context_builder: AgentContextBuilder | None = None,
    checkpointer: Any | None = None,
) -> object:
    nodes = AnalysisNodes(
        llm, database, retriever, python_analysis, dataset_store, result_history, agent_context_builder
    )
    return create_agent(
        model=LangChainChatModelAdapter(llm),
        tools=nodes.tool_registry.tools,
        system_prompt=AGENT_SYSTEM,
        middleware=[
            # 迭代预算由框架统一统计；领域中间件不再自行维护循环退出边。
            ModelCallLimitMiddleware(
                run_limit=retriever.settings.agent_max_iterations,
                exit_behavior="end",
            ),
            DataAgentMiddleware(nodes),
        ],
        state_schema=AnalysisState,
        checkpointer=checkpointer,
        name="data_analysis_agent",
    )
