"""分析流程的 LangGraph 状态图定义。

把输入安全检查、Agent 决策、工具调用、SQL 安全校验、人工审核、SQL 执行与
结果整理等节点编排成一张有向图，并定义节点之间的路由（条件边）。
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
    graph.add_node("sql_validate", nodes.sql_validate)
    graph.add_node("human_feedback", nodes.human_feedback)
    graph.add_node("sql_execute", nodes.sql_execute)
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
            if state.get("result_mode") == "need_clarification"
            else "sql_validate"
            if state.get("pending_sql_validation")
            else "agent_decide"
        ),
        {"result": "result", "sql_validate": "sql_validate", "agent_decide": "agent_decide"},
    )
    graph.add_conditional_edges(
        "sql_validate",
        _route_sql_validation,
        {
            "human_feedback": "human_feedback",
            "sql_execute": "sql_execute",
            "agent_decide": "agent_decide",
            "result": "result",
        },
    )
    graph.add_conditional_edges(
        "human_feedback",
        lambda state: "sql_execute" if state.get("human_feedback", {}).get("approved", True) else "agent_decide",
        {"sql_execute": "sql_execute", "agent_decide": "agent_decide"},
    )
    graph.add_edge("sql_execute", "agent_decide")
    graph.add_edge("result", END)
    return graph


def _route_sql_validation(state: AnalysisState) -> str:
    if state.get("safety", {}).get("passed"):
        return "human_feedback" if state.get("human_review_enabled") else "sql_execute"
    if state.get("error"):
        return "result"
    return "agent_decide"
