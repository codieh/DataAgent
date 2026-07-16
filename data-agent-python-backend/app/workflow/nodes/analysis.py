"""分析工作流节点实现。

本模块实现 ``AnalysisNodes``，是 LangGraph 各节点的具体逻辑落地：
- ``input_guard``：输入侧提示注入安全校验；
- ``agent_decide``：Agent 决策循环核心，调用 LLM 选定下一步工具或结束；
- ``sql_validate`` / ``human_feedback`` / ``sql_execute``：SQL 安全校验、人工审核、执行；
- ``result``：汇总多查询结果，调用 LLM 生成结构化分析报告。

每个节点接收 ``AnalysisState`` 并返回需要合并进全局状态的状态增量（dict）。
模块级辅助函数负责上下文投影、观察记录、结果清洗与合并等纯逻辑。
"""

import asyncio
import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from app.infrastructure.datasource.sql import BusinessDatabase
from app.analysis import AnalysisDatasetStore
from app.analysis.service import PythonAnalysisService
from app.context import estimate_tokens
from app.retrieval import KnowledgeRetriever
from app.security import PromptInjectionGuard
from app.workflow.prompts import (
    AGENT_SYSTEM,
    RESULT_STRUCTURE_SYSTEM,
    RESULT_SUMMARY_SYSTEM,
)
from app.workflow.state import AnalysisState
from app.workflow.tools import AnalysisToolRegistry
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

    async def agent_decide(self, state: AnalysisState) -> dict[str, Any]:
        """Agent 决策循环核心：决定本轮是调用某个工具还是结束。

        处理层级：
        1. 达到最大迭代轮次则强制 finish；
        2. 构建面向模型的上下文并请求工具调用；
        3. 若尚无 schema 却要查表/执行 SQL，则强制改为 search_schema（先了解结构）；
        4. schema 检索或 SQL 执行达到上限则强制 finish；
        5. 若因上述规则改写了动作/参数，则同步修正 LLM 返回的工具调用；
        6. finish 时落定 ``final_answer`` 与 ``result_mode``。
        """
        iteration = state.get("agent_iterations", 0)
        _progress("agent_decide", f"正在决定第 {iteration + 1} 步分析动作")
        if iteration >= self.retriever.settings.agent_max_iterations:
            # 超出轮次预算：使用既有结论收尾，并据“是否已拿到数据行”推断结果模式
            final_answer = state.get("final_answer") or "分析达到最大轮次，已返回当前可确认的结果。"
            return {
                "agent_decision": {"action": "finish", "reasonSummary": "已达到分析轮次上限"},
                "final_answer": final_answer,
                "result_mode": state.get("result_mode") or ("success" if state.get("rows") else "budget_exhausted"),
                "messages": [AIMessage(content=final_answer)],
            }
        if self.agent_context_builder is None:
            raise RuntimeError("AgentContextBuilder 未配置")
        context = await self.agent_context_builder.build(state)
        writer = get_stream_writer()
        streamed_final = False

        def on_text_delta(delta: str) -> None:
            """只有模型直接回答时才会收到文本增量；工具调用的 content 被协议要求为空。"""
            nonlocal streamed_final
            if not streamed_final:
                writer({"type": "final_answer.started", "stage": "agent_decide", "data": {}})
                streamed_final = True
            writer({"type": "final_answer.delta", "stage": "agent_decide", "data": {"delta": delta}})

        # 让 LLM 以原生工具调用方式决定下一步动作
        response = await self.llm.complete_tool_messages(
            AGENT_SYSTEM,
            context.messages,
            tools=self.tool_registry.specifications(),
            on_text_delta=on_text_delta,
        )
        tool_call = response.tool_calls[0] if response.tool_calls else None
        # 没有工具调用即视为结束本轮 Agent 循环
        action = tool_call["name"] if tool_call else "finish"
        arguments = tool_call["args"] if tool_call else {}
        # 安全护栏：还没检索过 schema 时，不允许直接 inspect/execute，强制先 search_schema
        if not state.get("schema", {}).get("tables") and action in {
            "inspect_tables",
            "execute_sql",
        }:
            action = "search_schema"
            arguments = {"query": state.get("contextualized_query") or state["query"]}
        # 检索/schema 预算耗尽则强制结束
        if (
            action == "search_schema"
            and state.get("schema_search_count", 0) >= self.retriever.settings.agent_max_schema_searches
        ):
            action = "finish"
            response = AIMessage(content="已达到表结构检索上限，请补充更明确的业务实体或指标。")
        if (
            action == "execute_sql"
            and state.get("sql_execution_count", 0) >= self.retriever.settings.agent_max_sql_executions
        ):
            action = "finish"
            response = AIMessage(content="已达到查询执行上限，已返回当前可确认的分析结果。")
        elif tool_call and (action != tool_call["name"] or arguments != tool_call["args"]):
            # 动作/参数被护栏改写后，需要把 LLM 返回的工具调用同步修正，保证图状态一致
            response = AIMessage(
                content=response.content,
                tool_calls=[{"id": tool_call["id"], "name": action, "args": arguments}],
            )
        updates: dict[str, Any] = {
            # 记录本轮决策（动作、理由摘要、参数）供后续节点与人工审核使用
            "agent_decision": {
                "action": action,
                "reasonSummary": str(response.content or ""),
                "arguments": arguments,
            },
            "agent_iterations": iteration + 1,
            "messages": [response],
        }
        if action == "finish":
            # 收尾：落定最终答案；若全程未产生查询结果，则按“对话”模式而非成功模式
            updates["final_answer"] = str(response.content or "") or (
                "分析已结束，但模型没有返回可展示的结论。"
            )
            # 真实流式响应结束后发送完成标记；本地护栏生成的固定文本则一次性发布。
            if not streamed_final:
                writer({"type": "final_answer.started", "stage": "agent_decide", "data": {}})
                writer({
                    "type": "final_answer.delta",
                    "stage": "agent_decide",
                    "data": {"delta": updates["final_answer"]},
                })
            writer({
                "type": "final_answer.completed",
                "stage": "agent_decide",
                "data": {"text": updates["final_answer"]},
            })
            if not state.get("query_results"):
                updates["result_mode"] = state.get("result_mode") or "conversation"
        return updates

    async def sql_validate(self, state: AnalysisState) -> dict[str, Any]:
        """对已生成的 SQL 做安全校验（只读、行数限制、敏感字段等）。

        返回安全通过时的规范化结果（含 ``pending_sql_execution=True``），
        或不通过时记录观察并标记 ``retryable`` 以触发自动修复/失败收敛。
        """
        _progress("sql_validate", "正在检查 SQL 安全性")
        from app.security import inspect_select_sql

        proposed_sql = str(state.get("sql") or "")
        policy = inspect_select_sql(
            proposed_sql,
            row_limit=self.database.settings.sql_row_limit,
            schema=state.get("schema", {}),
            sensitive_fields=self.retriever.settings.sql_sensitive_field_list,
        )
        if not policy.passed:
            # 计算已修复次数；可重试且超过最大修复次数则视为“修复已耗尽”
            repair_count = state.get("retry_count", 0) + (1 if policy.retryable else 0)
            repair_exhausted = policy.retryable and repair_count > self.retriever.settings.agent_max_sql_repairs
            observation = {
                "tool": "execute_safe_sql",
                "ok": False,
                "resultMode": policy.result_mode,
                "error": policy.reason,
                "retryable": policy.retryable and not repair_exhausted,
            }
            updates = {
                "sql": proposed_sql,
                "sql_error": policy.reason,
                "pending_sql_validation": False,
                "safety": {
                    "passed": False,
                    "reason": policy.reason,
                    "checks": policy.checks,
                    "resultMode": policy.result_mode,
                },
                "observations": _append_observation(state, observation),
                "pending_sql_execution": False,
                "retry_count": repair_count,
            }
            if not policy.retryable or repair_exhausted:
                # 不可重试或修复已耗尽：确定最终 result_mode 与错误文案
                updates["result_mode"] = policy.result_mode if not repair_exhausted else "sql_repair_exhausted"
                updates["error"] = (
                    policy.reason
                    if not repair_exhausted
                    else f"SQL 连续校验失败，已停止自动修复：{policy.reason}"
                )
            return updates
        safe_sql = policy.sql
        # 安全通过：写入规范化后的 SQL，并标记可进入执行阶段
        return {
            "sql": safe_sql,
            "sql_error": None,
            "pending_sql_validation": False,
            "pending_sql_execution": True,
            "safety": {
                "passed": True,
                "readOnly": True,
                "limitApplied": "LIMIT" in safe_sql.upper(),
                "sensitiveFields": [],
                "checks": policy.checks,
            },
        }

    async def human_feedback(self, state: AnalysisState) -> dict[str, Any]:
        """人工审核节点：若开启审核则以 interrupt 暂停等待审批，否则直接通过。

        审批不通过时记录观察并写入 plan 的 ``review_feedback``，阻止进入 SQL 执行。
        """
        if not state.get("human_review_enabled"):
            return {"human_feedback": {"approved": True, "comment": ""}}
        _progress("human_feedback", "SQL 已通过安全检查，等待人工审核")
        # 把待审核信息（SQL/计划/安全结论/所选表）交给人工，暂停工作流直到 resume
        feedback = interrupt(
            {
                "sql": state.get("sql"),
                "plan": state.get("plan"),
                "safety": state.get("safety"),
                "tables": state.get("selected_tables", []),
            }
        )
        normalized = dict(feedback or {})
        updates: dict[str, Any] = {"human_feedback": normalized}
        if not normalized.get("approved", False):
            # 审核未通过：取消执行，并把审核意见写回计划，便于后续澄清/重试
            updates["pending_sql_execution"] = False
            plan = dict(state.get("plan") or {})
            plan["review_feedback"] = normalized.get("comment") or "人工审核未通过"
            updates["plan"] = plan
            updates["observations"] = _append_observation(
                state,
                {
                    "tool": "human_review",
                    "ok": False,
                    "error": normalized.get("comment") or "人工审核未通过",
                    "retryable": True,
                },
            )
        return updates

    async def sql_execute(self, state: AnalysisState) -> dict[str, Any]:
        """执行已通过校验/审核的 SQL，并把结果落库为分析数据集。

        成功：写入预览行、query_results、analysis_datasets，并累加 SQL 执行次数；
        失败：记录可重试的观察与异常，供上层决定修复或收敛。
        """
        _progress("sql_execute", "正在执行 SQL")
        try:
            row_limit = self.database.settings.sql_row_limit
            columns, rows = await self.database.execute_select(state["sql"], row_limit=row_limit)
            if self.dataset_store is None:
                raise RuntimeError("分析数据集存储未配置")
            dataset = await self.dataset_store.create(run_id=state["run_id"], columns=columns, rows=rows)
            preview = dataset["previewRows"]
            query_result = {
                "sql": state["sql"],
                "columns": columns,
                "rowCount": len(rows),
                "datasetId": dataset["id"],
                "dataset": {
                    "id": dataset["id"],
                    "rowCount": dataset["rowCount"],
                    "filePath": dataset["filePath"],
                },
            }
            # 成功路径：把结果集登记到 query_results，并累积进分析数据集列表
            return {
                "columns": columns,
                "rows": preview,
                "sql_error": None,
                "result_mode": "success",
                "pending_sql_execution": False,
                "sql_execution_count": state.get("sql_execution_count", 0) + 1,
                "query_results": [*state.get("query_results", []), query_result],
                "analysis_datasets": [*state.get("analysis_datasets", []), dataset],
                "observations": _append_observation(
                    state,
                    {
                        "tool": "execute_safe_sql",
                        "ok": True,
                        "summary": f"查询成功，返回 {len(rows)} 行",
                        "rowCount": len(rows),
                        "datasetId": dataset["id"],
                    },
                ),
            }
        except Exception as error:
            # 执行异常：返回可重试的观察，让 Agent 决定修复 SQL 或结束
            return {
                "columns": [],
                "rows": [],
                "sql_error": str(error),
                "retry_count": state.get("retry_count", 0) + 1,
                "pending_sql_execution": False,
                "sql_execution_count": state.get("sql_execution_count", 0) + 1,
                "observations": _append_observation(
                    state,
                    {"tool": "execute_safe_sql", "ok": False, "error": str(error), "retryable": True},
                ),
            }

    async def result(self, state: AnalysisState) -> dict[str, Any]:
        """汇总全部查询结果，调用 LLM 生成结构化分析报告（findings/metrics/charts）。

        三种分支：
        - 存在 ``error``：返回拦截/未执行占位分析；
        - 无数据行但有 ``final_answer``：直接返回模型结论（澄清/对话模式）；
        - 有数据行：并行流式生成总结、生成结构化指标与图表，再合并 Python 分析产物。
        """
        _progress("result", "正在整理分析结果")
        if state.get("error"):
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
        query_results = state.get("query_results") or []
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


def _append_observation(state: AnalysisState, observation: dict[str, Any]) -> list[dict[str, Any]]:
    """把一条工具观察追加到既有观察列表末尾（不可变地返回新列表）。"""
    return [*state.get("observations", []), observation]


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
