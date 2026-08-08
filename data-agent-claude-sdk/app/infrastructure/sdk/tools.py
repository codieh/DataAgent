"""Claude Agent SDK MCP 工具。

工具函数只负责把模型输入转换成领域服务调用，并返回稳定的结构化文本。
租户信息来自闭包中的 ``TenantContext``，不会从模型参数读取。
"""

import json
from typing import Any

from app.application.events import EventBroker
from app.application.goal_verifier import ResultVerifier
from app.config import get_settings
from app.domain.models import Goal, TenantContext
from app.infrastructure.analysis.sandbox import PythonSandbox
from app.infrastructure.datasource.mysql import BusinessDatabase
from app.infrastructure.persistence.database import ControlDatabase
from app.infrastructure.results.store import ResultStore
from app.infrastructure.retrieval.service import KnowledgeSearchService, SchemaSearchService
from app.security.sql_policy import inspect_select_sql

try:
    from claude_agent_sdk import create_sdk_mcp_server, tool
except ImportError:  # pragma: no cover - 运行时依赖缺失时由配置检查给出明确错误
    create_sdk_mcp_server = None
    tool = None


def _text_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}],
    }
    if is_error:
        result["is_error"] = True
    return result


class ToolFactory:
    def __init__(
        self,
        context: TenantContext,
        database: ControlDatabase,
        business_database: BusinessDatabase,
        result_store: ResultStore,
        events: EventBroker,
        schema_search: SchemaSearchService,
        knowledge_search: KnowledgeSearchService,
        verifier: ResultVerifier,
        python_sandbox: PythonSandbox | None = None,
    ):
        self.context = context
        self.control = database
        self.business = business_database
        self.result_store = result_store
        self.events = events
        self.schema_search = schema_search
        self.knowledge_search = knowledge_search
        self.verifier = verifier
        settings = get_settings()
        self.python_sandbox = python_sandbox or PythonSandbox(
            settings.python_sandbox_image,
            settings.python_sandbox_timeout_seconds,
        )

    def build_server(self):
        if tool is None or create_sdk_mcp_server is None:
            raise RuntimeError("未安装 claude-agent-sdk，请先执行 uv sync")

        @tool(
            "set_analysis_goal",
            "保存用户的数据分析目标，必须在执行 SQL 前调用。",
            {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "metrics": {"type": "array", "items": {"type": "object"}},
                    "dimensions": {"type": "array", "items": {"type": "string"}},
                    "filters": {"type": "array", "items": {"type": "object"}},
                    "time_range": {"type": "object"},
                    "ranking": {"type": "object"},
                    "limit": {"type": ["integer", "null"], "minimum": 1},
                    "expected_tables": {"type": "array", "items": {"type": "string"}},
                    "expected_output": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["goal"],
            },
        )
        async def set_analysis_goal(args: dict[str, Any]) -> dict[str, Any]:
            goal = Goal(
                goal=str(args.get("goal", "")).strip(),
                metrics=list(args.get("metrics") or []),
                dimensions=[str(item) for item in args.get("dimensions") or []],
                filters=list(args.get("filters") or []),
                time_range=dict(args.get("time_range") or {}),
                ranking=dict(args.get("ranking") or {}),
                limit=int(args["limit"]) if args.get("limit") is not None else None,
                expected_tables=[str(item) for item in args.get("expected_tables") or []],
                expected_output=[str(item) for item in args.get("expected_output") or []],
            )
            if not goal.goal:
                return _text_result({"status": "invalid", "message": "分析目标不能为空"}, is_error=True)
            await self.control.save_goal(self.context, goal)
            await self.events.publish(self.context, "analysis.goal.set", goal.as_dict())
            return _text_result({"status": "success", "analysis_goal": goal.as_dict()})

        @tool(
            "discover_schema",
            "发现数据库表。mode=catalog 浏览全表目录，mode=relevance 根据问题召回候选表。",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "mode": {"type": "string", "enum": ["catalog", "relevance"]},
                },
            },
        )
        async def discover_schema(args: dict[str, Any]) -> dict[str, Any]:
            mode = str(args.get("mode") or "relevance")
            if mode not in {"catalog", "relevance"}:
                return _text_result({"status": "invalid", "message": "mode 只能是 catalog 或 relevance"}, is_error=True)
            snapshot = await self.business.schema_snapshot(self.context.tenant_id)
            if mode == "catalog":
                data = [{"name": table["name"], "comment": table.get("comment", "")} for table in snapshot["tables"]]
                payload = {"status": "success", "mode": mode, "tables": data, "table_count": len(data)}
            else:
                data = self.schema_search.search(str(args.get("query") or ""), snapshot)
                payload = {"status": "success", "mode": mode, **data, "table_count": len(data["tables"])}
            await self.events.publish(self.context, "schema.discovered", {"mode": mode, "table_count": payload["table_count"]})
            return _text_result(payload)

        @tool(
            "inspect_schema",
            "读取指定真实表的字段、类型、注释和外键。",
            {"type": "object", "properties": {"tables": {"type": "array", "items": {"type": "string"}}}, "required": ["tables"]},
        )
        async def inspect_schema(args: dict[str, Any]) -> dict[str, Any]:
            requested = {str(item) for item in args.get("tables") or [] if str(item).strip()}
            snapshot = await self.business.schema_snapshot(self.context.tenant_id)
            tables = [table for table in snapshot["tables"] if table["name"] in requested]
            payload = {"status": "success", "tables": tables, "missing": sorted(requested - {t["name"] for t in tables})}
            await self.events.publish(self.context, "schema.inspected", {"tables": [table["name"] for table in tables]})
            return _text_result(payload, is_error=not tables)

        @tool(
            "search_business_knowledge",
            "搜索业务规则、指标口径、状态定义和业务文档。",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        )
        async def search_business_knowledge(args: dict[str, Any]) -> dict[str, Any]:
            hits = self.knowledge_search.search(str(args.get("query") or ""), limit=int(args.get("limit") or 6))
            await self.events.publish(self.context, "knowledge.searched", {"hit_count": len(hits)})
            return _text_result({"status": "success", "hits": hits, "hit_count": len(hits)})

        @tool(
            "execute_sql",
            "执行只读 SQL。系统会自动进行 SQLPolicy、租户权限和结果目标校验。",
            {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
        )
        async def execute_sql(args: dict[str, Any]) -> dict[str, Any]:
            sql = str(args.get("sql") or "").strip()
            goal = await self.control.get_goal(self.context)
            if goal is None:
                return _text_result({"status": "needs_revision", "message": "执行 SQL 前必须先调用 set_analysis_goal"}, is_error=True)
            snapshot = await self.business.schema_snapshot(self.context.tenant_id)
            policy = inspect_select_sql(
                sql,
                row_limit=get_settings().max_sql_rows,
                schema=snapshot,
                sensitive_fields=get_settings().allowed_sensitive_fields,
            )
            if not policy.passed:
                payload = {
                    "status": "blocked",
                    "code": policy.code,
                    "reason": policy.reason,
                    "retryable": policy.retryable,
                    "checks": policy.checks,
                }
                await self.events.publish(self.context, "sql.validation_failed", payload)
                return _text_result(payload, is_error=True)

            try:
                query_result = await self.business.execute(
                    self.context.tenant_id, policy.sql, get_settings().max_sql_rows
                )
            except Exception as error:  # noqa: BLE001 - SQL 驱动错误需要结构化返回给 Agent
                await self.events.publish(self.context, "sql.failed", {"error": str(error)})
                return _text_result({"status": "failed", "code": "sql_execution_error", "message": str(error)}, is_error=True)

            verification = self.verifier.verify(goal, policy.sql, query_result)
            result_id, path = await self.result_store.save(self.context, query_result)
            await self.control.save_result_set(
                self.context,
                result_id,
                str(path),
                query_result.columns,
                query_result.row_count,
                query_result.truncated,
                f"查询返回 {query_result.row_count} 行",
                {
                    "status": verification.status,
                    "checks": verification.checks,
                    "mismatches": verification.mismatches,
                },
            )
            # SQL 结果也是 Run 产生的正式产物；result_sets 仅作为分页读取的专用索引保留。
            await self.control.save_artifact(
                self.context,
                result_id,
                "sql_result",
                str(path),
                {
                    "artifact_ref": result_id,
                    "sql": policy.sql,
                    "columns": query_result.columns,
                    "row_count": query_result.row_count,
                    "truncated": query_result.truncated,
                    "verification": {
                        "status": verification.status,
                        "checks": verification.checks,
                        "mismatches": verification.mismatches,
                    },
                },
            )
            payload = {
                "artifact_kind": "sql_result",
                "artifact_ref": result_id,
                "status": verification.status,
                "sql": policy.sql,
                "row_count": query_result.row_count,
                "columns": query_result.columns,
                "preview": query_result.rows[:20],
                "result_ref": result_id,
                "truncated": query_result.truncated,
                "verification": {
                    "status": verification.status,
                    "checks": verification.checks,
                    "mismatches": verification.mismatches,
                },
                "available_actions": ["inspect_result", "analyze_result"],
            }
            await self.events.publish(
                self.context,
                "artifact.created",
                {
                    "artifact_ref": result_id,
                    "artifact_kind": "sql_result",
                    "row_count": query_result.row_count,
                    "truncated": query_result.truncated,
                },
            )
            await self.events.publish(
                self.context,
                "sql.executed",
                {
                    "artifact_ref": result_id,
                    # 保留旧字段，兼容已有会话和工具调用记录。
                    "result_ref": result_id,
                    **payload["verification"],
                    "row_count": query_result.row_count,
                },
            )
            return _text_result(payload, is_error=verification.status != "passed")

        @tool(
            "inspect_result",
            "根据 SQL 结果产物引用分页读取完整查询结果。",
            {
                "type": "object",
                "properties": {
                    "artifact_ref": {"type": "string", "description": "SQL 结果产物引用。"},
                    # 兼容历史上下文中的旧参数名；新调用优先使用 artifact_ref。
                    "result_ref": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                    "columns": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["artifact_ref"],
            },
        )
        async def inspect_result(args: dict[str, Any]) -> dict[str, Any]:
            artifact_ref = str(args.get("artifact_ref") or args.get("result_ref") or "")
            metadata = await self.control.get_result_set(self.context, artifact_ref)
            payload = await self.result_store.read(
                metadata["file_path"],
                offset=int(args.get("offset") or 0),
                limit=int(args.get("limit") or 50),
                columns=[str(item) for item in args.get("columns") or []] or None,
            )
            await self.events.publish(self.context, "result.inspected", {"artifact_ref": payload["result_id"], "result_ref": payload["result_id"], "offset": payload["offset"], "limit": payload["limit"]})
            return _text_result({"status": "success", **payload})

        @tool(
            "analyze_result",
            "在隔离 Python 沙箱中分析已保存的查询结果。大结果不应直接放入上下文，应使用此工具。",
            {
                "type": "object",
                "properties": {
                    "artifact_ref": {"type": "string", "description": "SQL 结果产物引用。"},
                    "result_ref": {"type": "string"},
                    "objective": {"type": "string"},
                    "code": {"type": "string", "description": "定义 analyze(data) 的 Python 代码"},
                },
                "required": ["artifact_ref", "objective", "code"],
            },
        )
        async def analyze_result(args: dict[str, Any]) -> dict[str, Any]:
            artifact_ref = str(args.get("artifact_ref") or args.get("result_ref") or "")
            metadata = await self.control.get_result_set(self.context, artifact_ref)
            payload = await self.result_store.read_all(metadata["file_path"], max_rows=get_settings().max_sql_rows)
            try:
                analysis = await self.python_sandbox.run(payload, str(args.get("code") or ""))
            except (RuntimeError, TypeError, ValueError) as error:
                await self.events.publish(self.context, "artifact.failed", {"result_ref": metadata["id"], "error": str(error)})
                return _text_result(
                    {"status": "failed", "code": "python_analysis_error", "message": str(error)},
                    is_error=True,
                )
            artifact = {
                "objective": str(args.get("objective") or ""),
                "source_artifact_ref": metadata["id"],
                "result_ref": metadata["id"],
                "row_count": payload["row_count"],
                "analysis": analysis,
            }
            artifact_id, artifact_path = await self.result_store.save_artifact(self.context, "python_analysis", artifact)
            await self.control.save_artifact(self.context, artifact_id, "python_analysis", str(artifact_path), artifact)
            await self.events.publish(self.context, "artifact.created", {"artifact_ref": artifact_id, "result_ref": metadata["id"]})
            return _text_result({"status": "success", "artifact_ref": artifact_id, "analysis": artifact})

        @tool(
            "search_history",
            "搜索当前用户可访问的历史会话、历史运行和历史结果。",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "scope": {"type": "string", "enum": ["auto", "current", "all", "messages", "results"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
        )
        async def search_history(args: dict[str, Any]) -> dict[str, Any]:
            scope = str(args.get("scope") or "auto")
            if scope == "all":
                scope = "auto"
            if scope not in {"auto", "current", "messages", "results"}:
                return _text_result({"status": "invalid", "message": "scope 不合法"}, is_error=True)
            hits = await self.control.search_history(
                self.context.tenant_id,
                self.context.user_id,
                self.context.conversation_id,
                str(args.get("query") or ""),
                scope,
                int(args.get("limit") or 10),
            )
            await self.events.publish(self.context, "history.searched", {"scope": scope, "hit_count": len(hits)})
            return _text_result({"status": "success", "scope": scope, "hits": hits, "hit_count": len(hits)})

        @tool(
            "read_conversation_context",
            "读取当前会话指定消息附近的历史上下文。",
            {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "before": {"type": "integer", "minimum": 0, "maximum": 50},
                    "after": {"type": "integer", "minimum": 0, "maximum": 50},
                },
                "required": ["message_id"],
            },
        )
        async def read_conversation_context(args: dict[str, Any]) -> dict[str, Any]:
            messages = await self.control.read_message_context(
                self.context.tenant_id,
                self.context.user_id,
                self.context.conversation_id,
                str(args.get("message_id") or ""),
                int(args.get("before") or 3),
                int(args.get("after") or 3),
            )
            return _text_result({"status": "success", "messages": messages})

        @tool(
            "rewrite_core_memory",
            "整体读取并改写当前用户的跨会话核心记忆。",
            {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]},
        )
        async def rewrite_core_memory(args: dict[str, Any]) -> dict[str, Any]:
            content = str(args.get("content") or "").strip()
            if len(content) > 20_000:
                return _text_result({"status": "invalid", "message": "核心记忆不能超过 20000 个字符"}, is_error=True)
            await self.control.replace_memory(self.context.tenant_id, self.context.user_id, content)
            await self.events.publish(self.context, "memory.updated", {"content_length": len(content)})
            return _text_result({"status": "success", "content_length": len(content)})

        tools = [
            set_analysis_goal,
            discover_schema,
            inspect_schema,
            search_business_knowledge,
            execute_sql,
            inspect_result,
            analyze_result,
            search_history,
            read_conversation_context,
            rewrite_core_memory,
        ]
        return create_sdk_mcp_server(name="data_agent", version="0.1.0", tools=tools)
