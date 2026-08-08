"""分析工作流节点实现。

本模块实现 ``AnalysisNodes``，是 LangGraph 各节点的具体逻辑落地：
- ``input_guard``：输入侧提示注入安全校验；
- ``result``：汇总多查询结果，调用 LLM 生成结构化分析报告。

Agent 决策和工具循环由 ``create_agent`` 负责，调用前后的领域规则位于
``DataAgentMiddleware``。本模块只保留确定性的输入检查与结果生成。
"""

import asyncio
import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from langgraph.config import get_stream_writer

from app.infrastructure.datasource.sql import BusinessDatabase
from app.analysis import AnalysisDatasetStore
from app.analysis.service import PythonAnalysisService
from app.context import estimate_tokens
from app.domain.errors import InvalidOperationError
from app.retrieval import KnowledgeRetriever
from app.security import PromptInjectionGuard
from app.workflow.prompts import RESULT_STRUCTURE_SYSTEM, RESULT_SUMMARY_SYSTEM
from app.workflow.state import AnalysisState
from app.workflow.tools import AnalysisToolRegistry
from app.workflow.tool_metadata import tool_metadata
from app.workflow.ports import LlmClient
from app.workflow.outputs import AnalysisStructureOutput
from app.workflow.context_builder import AgentContextBuilder
from app.memory.core import CoreMemoryService


class AnalysisNodes:
    """分析工作流的全部节点实现。

    构造时装配好所需的依赖（LLM 客户端、数据库、检索器、Python 分析服务、
    数据集存储、结果历史、Agent 上下文构建器），并把它们封装进一个
    ``AnalysisToolRegistry`` 供 Agent 调用。所有节点方法均为异步，返回状态增量。
    """

    def __init__(
        self,
        llm: LlmClient,
        database: BusinessDatabase,
        retriever: KnowledgeRetriever,
        python_analysis: PythonAnalysisService | None = None,
        dataset_store: AnalysisDatasetStore | None = None,
        result_history: Any | None = None,
        agent_context_builder: AgentContextBuilder | None = None,
    ):
        self.llm = llm
        self.database = database
        self.retriever = retriever
        self.prompt_guard = PromptInjectionGuard(retriever.settings.prompt_max_query_chars)
        self.tool_registry = AnalysisToolRegistry(
            database,
            retriever,
            python_analysis,
            dataset_store,
            result_history,
            CoreMemoryService(retriever.settings, llm),
        )
        self.dataset_store = dataset_store
        self.result_history = result_history
        self.agent_context_builder = agent_context_builder

    async def input_guard(self, state: AnalysisState) -> dict[str, Any]:
        """输入侧安全校验：检测用户查询是否含提示注入。

        返回 {``result_mode``: "blocked_prompt_injection", ``error``, ``security``}，
        或 {``security``: {passed: True}} 表示放行。
        """
        _progress("input_guard", "正在检查请求安全性")
        inspection = self.prompt_guard.inspect(state.get("query", ""))
        if inspection.blocked:
            return {
                "result_mode": "blocked_prompt_injection",
                "error": inspection.reason,
                "security": {"passed": False, "type": "prompt_injection", "reason": inspection.reason},
            }
        return {"security": {"passed": True, "type": "input_guard"}}

    async def result(self, state: AnalysisState) -> dict[str, Any]:
        """汇总全部查询结果，调用 LLM 生成结构化分析报告（findings/metrics/charts）。

        三种分支：
        - 没有成功结果且存在 ``error``：返回拦截/未执行占位分析；
        - 无数据行但有 ``final_answer``：直接返回模型结论（澄清/对话模式）；
        - 有数据行：并行流式生成总结、生成结构化指标与图表，再合并 Python 分析产物。

        ``error`` 可能来自同一 Run 中较早的失败尝试，不能覆盖随后已经持久化的
        ``query_results``。是否执行成功必须以结果集为准，而不是依赖调用方清空旧字段。
        """
        _progress("result", "正在整理分析结果")
        query_results = state.get("query_results") or []
        if _should_render_terminal_error(state):
            blocked = state.get("result_mode") == "blocked_prompt_injection"
            return {
                "analysis": {
                    "title": "请求已拦截" if blocked else "查询未执行",
                    "summary": (
                        "请求包含试图修改系统规则或获取内部信息的内容，"
                        "系统未调用模型、未生成 SQL，也未访问业务数据。"
                        if blocked
                        else state["error"]
                    ),
                    "findings": [],
                    "metrics": [],
                    "charts": [],
                }
            }
        if not state.get("rows") and state.get("final_answer"):
            return {
                "analysis": {
                    "title": (
                        "需要补充信息"
                        if state.get("result_mode") == "need_clarification"
                        else "分析结果"
                    ),
                    "summary": state["final_answer"],
                    "findings": [],
                    "metrics": [],
                    "charts": [],
                }
            }
        inspected_results: dict[str, dict[str, Any]] = {}
        if self.result_history is not None:
            # 逐个结果集读取完整明细（最多 50 行预览），用于后续综合解释，而非只看最后一项
            for query_result in query_results:
                dataset_id = query_result.get("datasetId")
                if dataset_id:
                    inspected_results[dataset_id] = await self.result_history.inspect(
                        state["conversation_id"], dataset_id, 0, 50
                    )
        payload = _build_result_payload(
            state.get("contextualized_query") or state["query"],
            query_results,
            inspected_results,
        )
        payload["python_analyses"] = [item.get("result", {}) for item in state.get("python_analyses", [])]
        serialized_payload = json.dumps(payload, ensure_ascii=False, default=_json_default)
        writer = get_stream_writer()

        async def stream_summary() -> str:
            """流式生成用户可见总结，并把增量交给 LangGraph custom stream。"""
            writer({"type": "final_answer.started", "stage": "result", "data": {}})
            parts: list[str] = []
            async for delta in self.llm.stream_complete(RESULT_SUMMARY_SYSTEM, serialized_payload):
                parts.append(delta)
                writer({"type": "final_answer.delta", "stage": "result", "data": {"delta": delta}})
            summary = "".join(parts).strip()
            if not summary:
                raise RuntimeError("最终分析总结为空")
            writer({"type": "final_answer.completed", "stage": "result", "data": {"text": summary}})
            return summary

        # TaskGroup 保证任一路失败时立即取消另一路，避免失败后仍继续消耗模型请求。
        async with asyncio.TaskGroup() as tasks:
            summary_task = tasks.create_task(stream_summary())
            structure_task = tasks.create_task(self.llm.complete_model(
                AnalysisStructureOutput,
                RESULT_STRUCTURE_SYSTEM,
                serialized_payload,
            ))
        summary, structure = summary_task.result(), structure_task.result()
        analysis = {"summary": summary, **structure.model_dump(by_alias=True)}
        normalized = _normalize_analysis(
            analysis,
            [
                column
                # 以本次所有结果集的列作为图表字段的合法来源，避免编造不存在的字段
                for result in payload["results"]
                for column in result.get("columns", [])
            ] or state.get("columns", []),
        )
        # 把 Python 分析产出的指标/发现/图表并入最终结果
        return {"analysis": _merge_python_analysis(normalized, state.get("python_analyses", []))}


def _should_render_terminal_error(state: AnalysisState) -> bool:
    """只有不存在任何成功结果集时，顶层错误才能决定最终失败页面。"""
    return bool(state.get("error")) and not bool(state.get("query_results"))


def _build_result_payload(
    query: str,
    query_results: list[dict[str, Any]],
    inspected_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """构造最终回答的输入 payload。

    关键设计：保留多次查询的全部结果集（按 index 编号），而不是只取最后一项，
    以便 LLM 综合多个结果集作答。每个结果集尽量使用历史明细中的行数据。
    """
    results = []
    for index, query_result in enumerate(query_results, start=1):
        dataset_id = str(query_result.get("datasetId") or "")
        inspected = inspected_results.get(dataset_id, {})
        results.append(
            {
                "index": index,
                "resultSetId": dataset_id,
                "sql": query_result.get("sql", ""),
                "rowCount": inspected.get("rowCount", query_result.get("rowCount", 0)),
                "columns": inspected.get("columns", query_result.get("columns", [])),
                "rows": inspected.get("rows", []),
            }
        )
    return {"query": query, "results": results}

def _progress(stage: str, message: str) -> None:
    """向流式输出写入“阶段开始”事件，便于前端展示进度。"""
    get_stream_writer()({"type": "stage.started", "stage": stage, "message": message})


def _json_default(value: Any) -> Any:
    """``json.dumps`` 兜底序列化：把日期/Decimal/字节转换为可序列化形式。"""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _conversation_messages(state: AnalysisState, current_content: str) -> list[dict[str, str]]:
    """由近轮对话历史组装模型消息（仅 user/assistant），末尾追加当前上下文。"""
    messages = []
    for item in state.get("memory_context", {}).get("recentMessages", []):
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": current_content})
    return messages


def _supplemental_memory(state: AnalysisState) -> dict[str, Any]:
    """从 ``memory_context`` 提取补充记忆（摘要/相关消息/长期记忆）。"""
    context = state.get("memory_context", {})
    return {
        "summary": context.get("summary", ""),
        "relatedMessages": context.get("relatedMessages", []),
        "longTermMemories": context.get("longTermMemories", []),
    }


def _normalize_tool_calls(
    tool_calls: list[dict[str, Any]],
    *,
    state: AnalysisState,
    schema_search_limit: int,
    sql_execution_limit: int,
) -> list[dict[str, Any]]:
    """规范化一轮中的全部 Tool Call，同时保留可安全并行的独立调用。

    尚未取得 Schema 时，带显式表名的 ``inspect_tables`` 可以直接读取真实结构；
    ``execute_sql`` 仍不能越序执行，并会被替换为相关表召回。
    """
    normalized: list[dict[str, Any]] = []
    has_schema = bool(state.get("schema", {}).get("tables"))
    schema_requested = any(call["name"] == "search_schema" for call in tool_calls)
    replacement_added = False
    query = state.get("contextualized_query") or state["query"]

    for call in tool_calls:
        name = call["name"]
        has_explicit_tables = (
            name == "inspect_tables"
            and bool(call.get("args", {}).get("tables"))
        )
        if not has_schema and name in {"inspect_tables", "execute_sql"} and not has_explicit_tables:
            if not schema_requested and not replacement_added:
                normalized.append(
                    {
                        **call,
                        "name": "search_schema",
                        "args": {"query": query, "mode": "relevance"},
                    }
                )
                replacement_added = True
            continue
        normalized.append(call)

    if state.get("schema_search_count", 0) >= schema_search_limit:
        normalized = [call for call in normalized if call["name"] != "search_schema"]
    if state.get("sql_execution_count", 0) >= sql_execution_limit:
        normalized = [call for call in normalized if call["name"] != "execute_sql"]
    return normalized


def _validate_parallel_state_writes(tool_calls: list[dict[str, Any]]) -> None:
    """依据工具元数据拒绝不安全并发和 State 写集冲突。"""
    owners: dict[str, str] = {}
    for call in tool_calls:
        name = call["name"]
        metadata = tool_metadata(name)
        if len(tool_calls) > 1 and not metadata.concurrency_safe:
            raise InvalidOperationError(f"工具 {name} 不允许与其它工具并行执行。")
        for field in metadata.state_writes:
            previous = owners.get(field)
            if previous is not None:
                raise InvalidOperationError(
                    f"工具 {previous} 与 {name} 不能并行：都会更新状态字段 {field}。"
                )
            owners[field] = name


def _budget_exhausted_message(
    original_tool_calls: list[dict[str, Any]],
    state: AnalysisState,
    retriever: KnowledgeRetriever,
) -> str:
    """当本轮所有调用都被预算护栏移除时，返回可观测的结束原因。"""
    names = {call["name"] for call in original_tool_calls}
    if (
        "search_schema" in names
        and state.get("schema_search_count", 0) >= retriever.settings.agent_max_schema_searches
    ):
        return "已达到表结构检索上限，请补充更明确的业务实体或指标。"
    if (
        "execute_sql" in names
        and state.get("sql_execution_count", 0) >= retriever.settings.agent_max_sql_executions
    ):
        return "已达到查询执行上限，已返回当前可确认的分析结果。"
    return "当前工具调用不满足执行顺序或预算约束，已停止本轮分析。"


def _budget_schema(schema: dict[str, Any], budget: int) -> dict[str, Any]:
    """按 token 预算裁剪 schema（带表基础开销）。

    与 context_builder 中版本的区别：先估算“仅含表元信息、不含列”的表基础开销，
    若仅基础开销就超预算则跳过该表；再逐列累加，超预算即停止本表剩余列。
    保证尽量多地纳入完整表（含其基础元信息），避免只塞进半张表。
    """
    selected = []
    used = 0
    for table in schema.get("tables", []):
        compact = {**table, "columns": []}
        base_cost = estimate_tokens(json.dumps(compact, ensure_ascii=False, default=_json_default))
        # 已有表且加入本表基础开销即超预算，则后续表都不再纳入
        if selected and used + base_cost > budget:
            break
        used += base_cost
        for column in table.get("columns", []):
            cost = estimate_tokens(json.dumps(column, ensure_ascii=False, default=_json_default))
            if used + cost > budget:
                break
            compact["columns"].append(column)
            used += cost
        selected.append(compact)
        if used >= budget:
            break
    return {"tables": selected}


def _budget_knowledge(knowledge: dict[str, Any], budget: int) -> dict[str, Any]:
    """按 token 预算裁剪知识库；超预算条目整条跳过（不部分截取）。"""
    result = {"documents": [], "evidences": []}
    used = 0
    for kind in ("evidences", "documents"):
        for item in knowledge.get(kind, []):
            cost = estimate_tokens(json.dumps(item, ensure_ascii=False, default=_json_default))
            if used + cost > budget:
                continue
            result[kind].append(item)
            used += cost
    return result


def _normalize_analysis(analysis: dict[str, Any], columns: list[dict[str, Any]]) -> dict[str, Any]:
    """清洗 LLM 产出的分析：过滤掉引用了不存在字段的图表，并对缺失字段给默认值。

    - 若图表自带内联数据 ``data``，则无论字段是否匹配都保留；
    - 否则要求 xField 与全部 yField 都来自 ``columns``，避免编造数据。
    """
    column_names = {column.get("name") for column in columns}
    charts = []
    for chart in analysis.get("charts", []):
        x_field = chart.get("xField")
        y_fields = chart.get("yFields") or []
        inline_data = chart.get("data") if isinstance(chart.get("data"), list) else []
        if inline_data or (x_field in column_names and y_fields and all(field in column_names for field in y_fields)):
            charts.append(chart)
    return {
        "title": str(analysis.get("title") or "分析结果"),
        "summary": str(analysis.get("summary") or ""),
        "findings": analysis.get("findings") if isinstance(analysis.get("findings"), list) else [],
        "metrics": analysis.get("metrics") if isinstance(analysis.get("metrics"), list) else [],
        "charts": charts,
    }


def _merge_python_analysis(analysis: dict[str, Any], python_analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """把 Python 分析产出的指标/发现/图表合并进最终分析，并做数量上限截断。

    上限：metrics/findings 各 100 条，charts 20 条，防止结果无限膨胀。
    """
    for item in python_analyses:
        result = item.get("result", {})
        analysis["metrics"].extend(result.get("metrics", []))
        analysis["findings"].extend(result.get("findings", []))
        analysis["charts"].extend(result.get("charts", []))
    analysis["metrics"] = analysis["metrics"][:100]
    analysis["findings"] = analysis["findings"][:100]
    analysis["charts"] = analysis["charts"][:20]
    return analysis
