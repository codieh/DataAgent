import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from app.infrastructure.datasource.sql import BusinessDatabase, SqlPolicyError, validate_select_sql
from app.retrieval import KnowledgeRetriever
from app.security import PromptInjectionGuard
from app.workflow.prompts import (
    CHITCHAT_SYSTEM,
    INTENT_SYSTEM,
    PLANNER_SYSTEM,
    RESULT_SYSTEM,
    SCHEMA_RECALL_SYSTEM,
    SQL_SYSTEM,
)
from app.workflow.state import AnalysisState
from app.workflow.ports import LlmClient
from app.workflow.outputs import AnalysisOutput, IntentOutput, PlanOutput, SchemaRecallOutput, SqlOutput


class AnalysisNodes:
    def __init__(self, llm: LlmClient, database: BusinessDatabase, retriever: KnowledgeRetriever):
        self.llm = llm
        self.database = database
        self.retriever = retriever
        self.prompt_guard = PromptInjectionGuard(retriever.settings.prompt_max_query_chars)

    async def input_guard(self, state: AnalysisState) -> dict[str, Any]:
        _progress("input_guard", "正在检查请求安全性")
        inspection = self.prompt_guard.inspect(state.get("query", ""))
        if inspection.blocked:
            return {
                "result_mode": "blocked_prompt_injection",
                "error": inspection.reason,
                "security": {"passed": False, "type": "prompt_injection", "reason": inspection.reason},
            }
        return {"security": {"passed": True, "type": "input_guard"}}

    async def intent(self, state: AnalysisState) -> dict[str, Any]:
        _progress("intent", "正在理解问题")
        result = await self.llm.complete_model(IntentOutput, INTENT_SYSTEM, state["query"], max_tokens=512)
        classification = result.classification.upper()
        if classification not in {"DATA_ANALYSIS", "CHITCHAT"}:
            classification = "DATA_ANALYSIS"
        return {
            "intent": classification,
            "contextualized_query": result.contextualized_query or state["query"],
            "execution_path": "complex" if result.execution_path.lower() == "complex" else "simple",
        }

    async def schema_recall(self, state: AnalysisState) -> dict[str, Any]:
        _progress("schema_recall", "正在读取真实数据库结构")
        full_schema = await self.database.schema_snapshot()
        recalled = await self.retriever.search_schema(
            state.get("contextualized_query") or state["query"], full_schema
        )
        schema = {"tables": recalled["tables"]}
        selection = await self.llm.complete_model(
            SchemaRecallOutput,
            SCHEMA_RECALL_SYSTEM,
            json.dumps(
                {"query": state.get("contextualized_query") or state["query"], "schema": schema},
                ensure_ascii=False,
            ),
            max_tokens=800,
        )
        available = {item.get("name") for item in schema.get("tables", [])}
        selected = [name for name in selection.selected_tables if name in available]
        if not selected:
            selected = [table["name"] for table in recalled["tables"][: self.retriever.settings.recall_schema_top_k]]
        reasons = recalled["reasons"] | selection.reasons
        return {"schema": schema, "selected_tables": selected, "schema_reasons": reasons}

    async def knowledge_recall(self, state: AnalysisState) -> dict[str, Any]:
        _progress("knowledge_recall", "正在召回业务知识")
        query = state.get("contextualized_query") or state["query"]
        return {"knowledge": await self.retriever.search(query)}

    async def planner(self, state: AnalysisState) -> dict[str, Any]:
        _progress("planner", "正在制定分析计划")
        feedback = state.get("human_feedback") or {}
        user = json.dumps(
            {
                "query": state.get("contextualized_query") or state["query"],
                "schema": state.get("schema", {}),
                "knowledge": state.get("knowledge", {}),
                "review_feedback": feedback.get("comment"),
            },
            ensure_ascii=False,
        )
        plan_output = await self.llm.complete_model(PlanOutput, PLANNER_SYSTEM, user, max_tokens=1500)
        plan = plan_output.model_dump(by_alias=True)
        schema_tables = {item.get("name") for item in state.get("schema", {}).get("tables", [])}
        selected = [name for name in plan.get("selected_tables", []) if name in schema_tables]
        if not selected:
            selected = sorted(name for name in schema_tables if name)[:3]
        plan["selected_tables"] = selected
        if feedback.get("comment"):
            plan["review_feedback"] = feedback["comment"]
        return {"plan": plan, "selected_tables": selected, "human_feedback": {}}

    async def simple_plan(self, state: AnalysisState) -> dict[str, Any]:
        _progress("simple_plan", "正在准备单步查询")
        return {
            "plan": {
                "goal": state.get("contextualized_query") or state["query"],
                "successCriteria": ["查询成功执行并基于真实结果完成总结"],
                "selected_tables": state.get("selected_tables", []),
                "steps": [
                    {
                        "id": "step_01",
                        "index": 0,
                        "title": "执行数据查询",
                        "objective": state.get("contextualized_query") or state["query"],
                        "status": "pending",
                    }
                ],
            }
        }

    async def sql_generate(self, state: AnalysisState) -> dict[str, Any]:
        _progress("sql_generate", "正在生成 SQL")
        selected = set(state.get("selected_tables", []))
        schema = {
            "tables": [table for table in state.get("schema", {}).get("tables", []) if table.get("name") in selected]
        }
        user = json.dumps(
            {
                "query": state.get("contextualized_query") or state["query"],
                "plan": state.get("plan", {}),
                "schema": schema,
                "knowledge": state.get("knowledge", {}),
                "previous_error": state.get("sql_error"),
            },
            ensure_ascii=False,
        )
        result = await self.llm.complete_model(SqlOutput, SQL_SYSTEM, user, max_tokens=1800)
        return {
            "sql": result.sql,
            "sql_explanation": result.explanation,
            "sql_error": None,
        }

    async def sql_validate(self, state: AnalysisState) -> dict[str, Any]:
        _progress("sql_validate", "正在检查 SQL 安全性")
        try:
            safe_sql = validate_select_sql(state.get("sql", ""), self.database.settings.sql_row_limit)
        except SqlPolicyError as error:
            return {
                "result_mode": "blocked_unsafe_sql",
                "error": str(error),
                "safety": {"passed": False, "reason": str(error)},
            }
        return {
            "sql": safe_sql,
            "safety": {
                "passed": True,
                "readOnly": True,
                "limitApplied": "LIMIT" in safe_sql.upper(),
                "sensitiveFields": [],
                "checks": [
                    {"name": "select_only", "passed": True},
                    {"name": "single_statement", "passed": True},
                    {"name": "row_limit", "passed": True},
                ],
            },
        }

    async def human_feedback(self, state: AnalysisState) -> dict[str, Any]:
        if not state.get("human_review_enabled"):
            return {"human_feedback": {"approved": True, "comment": ""}}
        _progress("human_feedback", "SQL 已通过安全检查，等待人工审核")
        feedback = interrupt(
            {
                "sql": state.get("sql"),
                "plan": state.get("plan"),
                "safety": state.get("safety"),
                "tables": state.get("selected_tables", []),
            }
        )
        return {"human_feedback": dict(feedback or {})}

    async def sql_execute(self, state: AnalysisState) -> dict[str, Any]:
        _progress("sql_execute", "正在执行 SQL")
        try:
            columns, rows = await self.database.execute_select(state["sql"])
            return {"columns": columns, "rows": rows, "sql_error": None, "result_mode": "success"}
        except Exception as error:
            return {
                "columns": [],
                "rows": [],
                "sql_error": str(error),
                "retry_count": state.get("retry_count", 0) + 1,
            }

    async def result(self, state: AnalysisState) -> dict[str, Any]:
        _progress("result", "正在整理分析结果")
        if state.get("error"):
            blocked = state.get("result_mode") == "blocked_prompt_injection"
            return {
                "analysis": {
                    "title": "请求已拦截" if blocked else "查询未执行",
                    "summary": (
                        "请求包含试图修改系统规则或获取内部信息的内容，系统未调用模型、未生成 SQL，也未访问业务数据。"
                        if blocked
                        else state["error"]
                    ),
                    "findings": [],
                    "metrics": [],
                    "charts": [],
                }
            }
        payload = {
            "query": state.get("contextualized_query") or state["query"],
            "sql": state.get("sql"),
            "columns": state.get("columns", []),
            "rows": state.get("rows", [])[:50],
            "row_count": len(state.get("rows", [])),
        }
        analysis = await self.llm.complete_model(
            AnalysisOutput,
            RESULT_SYSTEM,
            json.dumps(payload, ensure_ascii=False, default=_json_default),
            max_tokens=2500,
        )
        return {"analysis": _normalize_analysis(analysis.model_dump(by_alias=True), state.get("columns", []))}

    async def chitchat(self, state: AnalysisState) -> dict[str, Any]:
        _progress("result", "正在回复")
        answer = await self.llm.complete(CHITCHAT_SYSTEM, state["query"], max_tokens=500)
        return {
            "result_mode": "free_chat",
            "analysis": {"title": "DataAgent", "summary": answer, "findings": [], "metrics": [], "charts": []},
        }


def _progress(stage: str, message: str) -> None:
    get_stream_writer()({"type": "stage.started", "stage": stage, "message": message})


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _normalize_analysis(analysis: dict[str, Any], columns: list[dict[str, Any]]) -> dict[str, Any]:
    column_names = {column.get("name") for column in columns}
    charts = []
    for chart in analysis.get("charts", []):
        x_field = chart.get("xField")
        y_fields = chart.get("yFields") or []
        if x_field in column_names and y_fields and all(field in column_names for field in y_fields):
            charts.append(chart)
    return {
        "title": str(analysis.get("title") or "分析结果"),
        "summary": str(analysis.get("summary") or ""),
        "findings": analysis.get("findings") if isinstance(analysis.get("findings"), list) else [],
        "metrics": analysis.get("metrics") if isinstance(analysis.get("metrics"), list) else [],
        "charts": charts,
    }
