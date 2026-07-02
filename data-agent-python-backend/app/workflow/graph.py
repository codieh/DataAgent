from langgraph.graph import END, START, StateGraph

from app.infrastructure.datasource.sql import BusinessDatabase
from app.retrieval import KnowledgeRetriever
from app.workflow.nodes.analysis import AnalysisNodes
from app.workflow.state import AnalysisState
from app.workflow.ports import LlmClient


def build_analysis_graph(
    llm: LlmClient, database: BusinessDatabase, retriever: KnowledgeRetriever
) -> StateGraph:
    nodes = AnalysisNodes(llm, database, retriever)
    graph = StateGraph(AnalysisState)
    graph.add_node("input_guard", nodes.input_guard)
    graph.add_node("intent", nodes.intent)
    graph.add_node("schema_recall", nodes.schema_recall)
    graph.add_node("knowledge_recall", nodes.knowledge_recall)
    graph.add_node("planner", nodes.planner)
    graph.add_node("simple_plan", nodes.simple_plan)
    graph.add_node("sql_generate", nodes.sql_generate)
    graph.add_node("sql_validate", nodes.sql_validate)
    graph.add_node("human_feedback", nodes.human_feedback)
    graph.add_node("sql_execute", nodes.sql_execute)
    graph.add_node("result", nodes.result)
    graph.add_node("chitchat", nodes.chitchat)

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges(
        "input_guard",
        lambda state: "result" if state.get("result_mode") == "blocked_prompt_injection" else "intent",
        {"result": "result", "intent": "intent"},
    )
    graph.add_conditional_edges(
        "intent",
        lambda state: "knowledge_recall" if state.get("intent") == "DATA_ANALYSIS" else "chitchat",
        {"knowledge_recall": "knowledge_recall", "chitchat": "chitchat"},
    )
    graph.add_edge("knowledge_recall", "schema_recall")
    graph.add_conditional_edges(
        "schema_recall",
        lambda state: "planner" if state.get("execution_path") == "complex" else "simple_plan",
        {"planner": "planner", "simple_plan": "simple_plan"},
    )
    graph.add_edge("planner", "sql_generate")
    graph.add_edge("simple_plan", "sql_generate")
    graph.add_edge("sql_generate", "sql_validate")
    graph.add_conditional_edges(
        "sql_validate",
        lambda state: "human_feedback" if state.get("safety", {}).get("passed") else "result",
        {"human_feedback": "human_feedback", "result": "result"},
    )
    graph.add_conditional_edges(
        "human_feedback",
        lambda state: "sql_execute" if state.get("human_feedback", {}).get("approved", True) else "planner",
        {"sql_execute": "sql_execute", "planner": "planner"},
    )
    graph.add_conditional_edges(
        "sql_execute",
        lambda state: "sql_generate"
        if state.get("sql_error") and state.get("retry_count", 0) <= 2
        else "result",
        {"sql_generate": "sql_generate", "result": "result"},
    )
    graph.add_edge("result", END)
    graph.add_edge("chitchat", END)
    return graph
