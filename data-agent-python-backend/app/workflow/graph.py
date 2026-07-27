"""分析流程的 LangGraph 状态图定义。

把输入安全检查、Agent 决策、原子工具调用与结果整理编排成有向图。
SQL 校验、人工审核和执行封装在 execute_sql 工具内部，保证一次 Tool Call
只对应一个最终 Tool Result。
"""

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import tools_condition

from app.infrastructure.datasource.sql import BusinessDatabase
from app.retrieval import KnowledgeRetriever
from app.workflow.nodes.analysis import AnalysisNodes
from app.workflow.state import AnalysisState
from app.workflow.ports import LlmClient
from app.workflow.tools import LoggingToolNode
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
) -> StateGraph:
    nodes = AnalysisNodes(
        llm, database, retriever, python_analysis, dataset_store, result_history, agent_context_builder
    )
    graph = StateGraph(AnalysisState)
    graph.add_node("input_guard", nodes.input_guard)
    graph.add_node("agent_decide", nodes.agent_decide)
    graph.add_node("tools", LoggingToolNode(nodes.tool_registry.tools))
    graph.add_node("result", nodes.result)

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges(
        "input_guard",
        lambda state: "result" if state.get("result_mode") == "blocked_prompt_injection" else "agent_decide",
        {"result": "result", "agent_decide": "agent_decide"},
    )
    graph.add_conditional_edges(
        "agent_decide",
        tools_condition,
        {
            "tools": "tools",
            "__end__": "result",
        },
    )
    graph.add_conditional_edges(
        "tools",
        lambda state: (
            "result"
            if state.get("result_mode") == "need_clarification" or state.get("error")
            else "agent_decide"
        ),
        {"result": "result", "agent_decide": "agent_decide"},
    )
    graph.add_edge("result", END)
    return graph
