import json
import logging
from typing import Any

from app.config import get_settings
from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.models import AnalysisRunModel, elapsed_ms, utc_now
from app.infrastructure.persistence.repository import Repository
from app.observability.context import current_run_id
from app.workflow.runtime import GraphRuntime


logger = logging.getLogger(__name__)


class GraphAnalysisExecutor:
    """Runs LangGraph and translates graph updates into persisted product artifacts."""

    def __init__(self, runtime: GraphRuntime):
        self.runtime = runtime

    async def run(self, run_id: str) -> None:
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run:
                return
            run.status = "running"
            run.started_at = utc_now()
            run.current_stage = "input_guard"
            await repository.save_run(run)
            await self._event(repository, run, "run.started", None, {"status": "running"})
            initial_state = {
                "run_id": run.id,
                "conversation_id": run.conversation_id,
                "query": run.question,
                "contextualized_query": run.question,
                "human_review_enabled": run.human_review_enabled,
                "retry_count": 0,
            }
            logger.info(
                "analysis run started: runId=%s conversationId=%s queryChars=%d humanReview=%s",
                run.id,
                run.conversation_id,
                len(run.question),
                run.human_review_enabled,
            )
        await self._consume(run_id, self.runtime.stream(run_id, initial_state), initial_state)

    async def resume_after_review(self, run_id: str) -> None:
        await self._resume(run_id, approved=True, comment="")

    async def replan_after_rejection(self, run_id: str, comment: str) -> None:
        await self._resume(run_id, approved=False, comment=comment)

    async def _resume(self, run_id: str, *, approved: bool, comment: str) -> None:
        state = await self.runtime.state(run_id)
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run or run.status == "cancelled":
                return
            run.status = "running"
            run.result_mode = None
            await repository.save_run(run)
        await self._consume(run_id, self.runtime.resume(run_id, approved, comment), state)

    async def _consume(self, run_id: str, stream, accumulated: dict[str, Any]) -> None:
        active_stages: dict[str, str] = {}
        run_token = current_run_id.set(run_id)
        try:
            async for mode, payload in stream:
                if mode == "custom":
                    await self._handle_custom(run_id, payload, active_stages)
                    continue
                if mode != "updates" or not isinstance(payload, dict):
                    continue
                if "__interrupt__" in payload:
                    await self._mark_waiting_review(run_id, accumulated)
                    return
                for node, delta in payload.items():
                    if not isinstance(delta, dict):
                        continue
                    accumulated.update(delta)
                    await self._persist_node_update(run_id, node, delta, accumulated, active_stages)
            await self._complete(run_id, accumulated)
        except Exception as error:
            await self._fail(run_id, error)
        finally:
            current_run_id.reset(run_token)

    async def _handle_custom(self, run_id: str, payload: Any, active_stages: dict[str, str]) -> None:
        if not isinstance(payload, dict) or payload.get("type") != "stage.started":
            return
        stage = str(payload.get("stage") or "unknown")
        message = str(payload.get("message") or "正在处理")
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run or run.status == "cancelled":
                return
            run.current_stage = stage
            await repository.save_run(run)
            stage_run = await repository.get_running_stage(run_id, stage)
            created = stage_run is None
            if created:
                stage_run = await repository.create_stage(run_id, stage, message)
            active_stages[stage] = stage_run.id
            if not created:
                return
            logger.info("analysis stage started: runId=%s stage=%s message=%s", run_id, stage, message)
            await self._event(repository, run, "stage.started", stage, {"message": message})

    async def _persist_node_update(
        self,
        run_id: str,
        node: str,
        delta: dict[str, Any],
        state: dict[str, Any],
        active_stages: dict[str, str],
    ) -> None:
        stage = node
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run or run.status == "cancelled":
                return
            if delta.get("contextualized_query"):
                run.contextualized_question = str(delta["contextualized_query"])
            run.current_stage = stage
            await repository.save_run(run)

            if node == "schema_recall" and delta.get("schema"):
                await self._artifact(
                    repository,
                    run,
                    stage,
                    "schema_snapshot",
                    "已读取真实数据库结构",
                    delta["schema"],
                )
                await self._persist_retrieval(repository, run, state)
            elif node == "knowledge_recall" and delta.get("knowledge") is not None:
                knowledge = delta["knowledge"]
                count = len(knowledge.get("documents", [])) + len(knowledge.get("evidences", []))
                await self._artifact(
                    repository,
                    run,
                    stage,
                    "knowledge_retrieval",
                    f"召回 {count} 条业务知识",
                    knowledge,
                )
            elif node in {"planner", "simple_plan"} and delta.get("plan"):
                plan = dict(delta["plan"])
                plan.setdefault("selected_tables", delta.get("selected_tables", []))
                await self._artifact(repository, run, stage, "plan", "分析计划已生成", plan)
            elif node == "sql_validate" and state.get("sql"):
                await self._artifact(
                    repository,
                    run,
                    stage,
                    "query_preview",
                    "SQL 已生成并完成安全检查",
                    {
                        "sql": state["sql"],
                        "status": "validated" if state.get("safety", {}).get("passed") else "blocked",
                        "scope": {
                            "datasource": "sales-db",
                            "tables": state.get("selected_tables", []),
                            "timeRange": "由 SQL 条件确定",
                        },
                        "safety": state.get("safety", {}),
                    },
                )
            elif node == "sql_execute" and not delta.get("sql_error"):
                await self._persist_query_result(repository, run, state)
            elif node in {"result", "chitchat"} and delta.get("analysis"):
                analysis = _json_safe(delta["analysis"])
                queries = await repository.list_queries(run.id)
                result_set_id = next((item.result_set_id for item in reversed(queries) if item.result_set_id), None)
                if result_set_id:
                    _attach_result_set_ids(analysis, result_set_id)
                await self._artifact(repository, run, "result", "analysis", str(analysis.get("title") or "分析结果"), analysis)
                summary = str(analysis.get("summary") or "")
                if summary:
                    await repository.add_message(
                        conversation_id=run.conversation_id,
                        run_id=run.id,
                        role="assistant",
                        content=summary,
                    )
                    await self._event(repository, run, "text.delta", "result", {"text": summary})

            stage_id = active_stages.pop(stage, None)
            stage_run = None
            if stage_id:
                from app.infrastructure.persistence.models import StageRunModel

                stage_run = await session.get(StageRunModel, stage_id)
            if stage_run is None:
                stage_run = await repository.get_running_stage(run_id, stage)
            if stage_run:
                finished = await repository.finish_stage(stage_run, _stage_message(node, delta))
                logger.info(
                    "analysis stage completed: runId=%s stage=%s attempt=%d durationMs=%s",
                    run_id,
                    stage,
                    finished.attempt,
                    finished.duration_ms,
                )
                await self._event(
                    repository,
                    run,
                    "stage.completed",
                    stage,
                    {"message": finished.message, "durationMs": finished.duration_ms},
                )

    async def _persist_retrieval(self, repository: Repository, run: AnalysisRunModel, state: dict[str, Any]) -> None:
        selected = set(state.get("selected_tables", []))
        schema_tables = state.get("schema", {}).get("tables", [])
        tables = []
        relations = []
        for table in schema_tables:
            if table.get("name") not in selected:
                continue
            tables.append(
                {
                    "name": table.get("name"),
                    "displayName": table.get("name"),
                    "score": None,
                    "reason": state.get("schema_reasons", {}).get(table.get("name"), "与当前问题相关"),
                    "columns": table.get("columns", []),
                }
            )
            for foreign_key in table.get("foreignKeys", []):
                for source, target in zip(
                    foreign_key.get("columns", []),
                    foreign_key.get("referredColumns", []),
                    strict=False,
                ):
                    relations.append(
                        {
                            "fromTable": table.get("name"),
                            "fromColumn": source,
                            "toTable": foreign_key.get("referredTable"),
                            "toColumn": target,
                        }
                    )
        await self._artifact(
            repository,
            run,
            "schema_recall",
            "retrieval",
            f"选择了 {len(tables)} 张相关数据表",
            {
                "tables": tables,
                "relations": relations,
                "documents": state.get("knowledge", {}).get("documents", []),
                "evidences": state.get("knowledge", {}).get("evidences", []),
            },
        )

    async def _persist_query_result(self, repository: Repository, run: AnalysisRunModel, state: dict[str, Any]) -> None:
        rows = _json_safe(state.get("rows", []))
        columns = _json_safe(state.get("columns", []))
        result_set = await repository.add_result_set(run_id=run.id, columns=columns, rows=rows)
        query = await repository.add_query(
            run_id=run.id,
            step_id="step_01",
            sql=state.get("sql", ""),
            status="success",
            attempt=state.get("retry_count", 0) + 1,
            duration_ms=None,
            row_count=len(rows),
            result_set_id=result_set.id,
            safety=state.get("safety", {}),
            error=None,
        )
        await self._artifact(
            repository,
            run,
            "sql_execute",
            "query",
            f"查询成功，返回 {len(rows)} 行",
            {
                "id": query.id,
                "sql": query.sql,
                "status": query.status,
                "attempt": query.attempt,
                "rowCount": query.row_count,
                "resultSetId": result_set.id,
                "safety": query.safety,
                "error": None,
            },
        )
        state["result_set_id"] = result_set.id

    async def _artifact(
        self,
        repository: Repository,
        run: AnalysisRunModel,
        stage: str,
        artifact_type: str,
        summary: str,
        payload: dict[str, Any],
    ):
        artifact = await repository.add_artifact(
            run_id=run.id,
            stage=stage,
            artifact_type=artifact_type,
            summary=summary,
            payload=_json_safe(payload),
        )
        await self._event(
            repository,
            run,
            "artifact.created",
            stage,
            {"artifactId": artifact.id, "artifactType": artifact_type, "summary": summary},
        )
        return artifact

    async def _mark_waiting_review(self, run_id: str, state: dict[str, Any]) -> None:
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run:
                return
            artifacts = await repository.list_artifacts(run_id)
            plan = next((item for item in reversed(artifacts) if item.type == "plan"), None)
            query = next((item for item in reversed(artifacts) if item.type == "query_preview"), None)
            review = await repository.create_review(
                run_id=run.id,
                plan_artifact_id=plan.id if plan else "",
                query_artifact_id=query.id if query else None,
                reason="SQL 已生成并通过安全检查，等待人工确认。",
            )
            run.status = "waiting_review"
            run.result_mode = "waiting_human_feedback"
            run.current_stage = "human_feedback"
            await repository.save_run(run)
            logger.info(
                "analysis run completed: runId=%s resultMode=%s durationMs=%s",
                run.id,
                run.result_mode,
                run.duration_ms,
            )
            await self._event(
                repository,
                run,
                "review.required",
                "human_feedback",
                {"reviewId": review.id, "status": "waiting"},
            )

    async def _complete(self, run_id: str, state: dict[str, Any]) -> None:
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run or run.status == "cancelled":
                return
            run.status = "completed"
            run.result_mode = state.get("result_mode") or "success"
            run.completed_at = utc_now()
            run.duration_ms = elapsed_ms(run.started_at, run.completed_at)
            await repository.save_run(run)
            await self._event(
                repository,
                run,
                "run.completed",
                "result",
                {"status": "completed", "resultMode": run.result_mode, "runUrl": f"/api/v1/runs/{run.id}"},
            )

    async def _fail(self, run_id: str, error: Exception) -> None:
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run or run.status == "cancelled":
                return
            run.status = "failed"
            run.result_mode = "execution_error"
            run.error_code = error.__class__.__name__
            run.error_message = str(error) or error.__class__.__name__
            run.completed_at = utc_now()
            run.duration_ms = elapsed_ms(run.started_at, run.completed_at)
            await repository.save_run(run)
            stage_run = await repository.get_running_stage(run_id, run.current_stage or "")
            if stage_run:
                await repository.fail_stage(stage_run, error)
            logger.exception(
                "analysis run failed: runId=%s stage=%s errorCode=%s durationMs=%s",
                run.id,
                run.current_stage,
                run.error_code,
                run.duration_ms,
                exc_info=error,
            )
            await self._event(
                repository,
                run,
                "run.failed",
                run.current_stage,
                {"code": run.error_code, "message": run.error_message},
            )

    async def _event(
        self,
        repository: Repository,
        run: AnalysisRunModel,
        event_type: str,
        stage: str | None,
        data: dict[str, Any],
    ) -> None:
        await repository.add_event(
            run_id=run.id,
            conversation_id=run.conversation_id,
            event_type=event_type,
            stage=stage,
            data=_json_safe(data),
        )


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _stage_message(node: str, delta: dict[str, Any]) -> str:
    messages = {
        "input_guard": "请求安全检查完成",
        "intent": "问题理解完成",
        "knowledge_recall": "业务知识召回完成",
        "schema_recall": "数据库结构读取完成",
        "planner": "分析计划已生成",
        "simple_plan": "单步执行方案已准备",
        "sql_generate": "SQL 已生成",
        "sql_validate": "SQL 安全检查完成",
        "human_feedback": "人工审核完成",
        "sql_execute": "SQL 执行完成" if not delta.get("sql_error") else "SQL 执行失败，准备修复",
        "result": "分析结果已生成",
        "chitchat": "回复已生成",
    }
    return messages.get(node, f"{node} 已完成")


def _attach_result_set_ids(analysis: dict[str, Any], result_set_id: str) -> None:
    for chart in analysis.get("charts", []):
        chart["resultSetId"] = result_set_id
    for metric in analysis.get("metrics", []):
        metric["sourceResultSetId"] = result_set_id
    for finding in analysis.get("findings", []):
        finding["sourceResultSetIds"] = [result_set_id]


settings = get_settings()
graph_runtime = GraphRuntime(settings)
workflow = GraphAnalysisExecutor(graph_runtime)
