"""分析运行的核心执行器：驱动 LangGraph 并落库产物。

本模块是「一次分析运行」的运行时引擎。它负责：
1. 从持久层加载运行（Run）上下文，构建 LangGraph 的初始状态（initial_state）。
2. 消费 GraphRuntime 产出的异步事件流（custom 事件 + 节点 updates）。
3. 将流式更新翻译为可持久化的产物（artifact）、阶段（stage）与事件（event），
   使前端可逐步回看分析过程。
4. 处理人工审核的中断（__interrupt__）、恢复（resume）与运行终态
   （completed / failed / waiting_review）的收尾。

设计要点：
- 每个公开方法（run / resume_after_review / replan_after_rejection）都通过
  _consume 统一消费事件流，保证落库逻辑集中且一致。
- 通过 current_run_id contextvar 在日志与可观测性链路中传递当前 run_id。
- 模块级辅助函数（_json_safe / _stage_message / _normalize_result_sources）为
  纯函数，负责序列化与阶段文案映射等无副作用的工具职责。
"""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from app.config import get_settings
from app.application.live_events import run_live_event_broker
from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.models import AnalysisRunModel, elapsed_ms, utc_now
from app.infrastructure.persistence.repository import Repository
from app.observability.context import current_run_id
from app.workflow.runtime import GraphRuntime


logger = logging.getLogger(__name__)


class GraphAnalysisExecutor:
    """分析运行执行器：运行 LangGraph 并把图更新翻译为持久化产物。"""

    def __init__(self, runtime: GraphRuntime):
        # 持有 LangGraph 运行时，负责状态构建、流式执行与恢复。
        self.runtime = runtime

    async def run(self, run_id: str) -> None:
        """启动一次全新的分析运行。

        加载运行与上下文，构建初始状态后交给 _consume 消费事件流。
        若运行记录不存在则直接返回（视为无效请求）。
        """
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run:
                return
            # 标记运行开始：进入输入安全校验阶段。
            run.status = "running"
            run.started_at = utc_now()
            run.current_stage = "input_guard"
            await repository.save_run(run)
            await self._event(repository, run, "run.started", None, {"status": "running"})
            conversation = await repository.get_conversation(run.conversation_id)
            # 取出触发本次运行的用户消息，用于构建记忆上下文。
            current_message = await repository.get_user_message_for_run(run.id)
            memory_context = await self.runtime.context_builder.build(
                repository=repository,
                conversation=conversation,
                current_message_id=current_message.id if current_message else None,
                query=run.question,
            )
            initial_state = {
                # 运行与会话标识，供下游节点与事件回写使用。
                "run_id": run.id,
                "conversation_id": run.conversation_id,
                "query": run.question,
                # 暂以原始问题作为上下文化问题初值，后续由规划节点改写。
                "contextualized_query": run.question,
                "memory_context": memory_context,
                "human_review_enabled": run.human_review_enabled,
                # 以下计数类字段用于重试/迭代等指标统计。
                "retry_count": 0,
                "agent_iterations": 0,
                "schema_search_count": 0,
                "sql_execution_count": 0,
                # 累积型产物容器，在事件流中被不断追加。
                "observations": [],
                "query_results": [],
                "python_analyses": [],
                "analysis_datasets": [],
            }
            logger.info(
                "analysis run started: runId=%s conversationId=%s queryChars=%d humanReview=%s "
                "memoryMessages=%d memoryRetrieved=%d memoryTokens=%d",
                run.id,
                run.conversation_id,
                len(run.question),
                run.human_review_enabled,
                memory_context["stats"]["recentCount"],
                memory_context["stats"]["retrievedCount"],
                memory_context["stats"]["estimatedTokens"],
            )
        # 进入统一消费流程：runtime.stream 产出事件流，initial_state 作为累加基线。
        await self._consume(run_id, self.runtime.stream(run_id, initial_state), initial_state)

    async def resume_after_review(self, run_id: str) -> None:
        """人工审核通过后的恢复：以「批准」语义继续图执行。"""
        await self._resume(run_id, approved=True, comment="")

    async def replan_after_rejection(self, run_id: str, comment: str) -> None:
        """人工审核驳回后的重规划：以「驳回」语义退回并依据意见重新规划。"""
        await self._resume(run_id, approved=False, comment=comment)

    async def _resume(self, run_id: str, *, approved: bool, comment: str) -> None:
        """恢复运行的内部入口：恢复运行状态后复用 _consume 消费 resume 事件流。"""
        # 先取回被中断时的图状态快照，供 resume 续跑。
        state = await self.runtime.state(run_id)
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            # 运行不存在或已被取消则不再恢复（幂等/安全保护）。
            if not run or run.status == "cancelled":
                return
            # 复位为运行中并清空上一轮 result_mode，等待本轮结果。
            run.status = "running"
            run.result_mode = None
            await repository.save_run(run)
        await self._consume(run_id, self.runtime.resume(run_id, approved, comment), state)

    async def _consume(self, run_id: str, stream, accumulated: dict[str, Any]) -> None:
        """消费 LangGraph 的事件流，将节点增量翻译为落库产物。

        参数:
            run_id: 当前运行 ID。
            stream: 异步迭代生成 (mode, payload) 的 LangGraph 事件流。
            accumulated: 跨事件累积的全量状态字典（节点增量会不断更新它）。
        """
        # 记录当前活跃阶段（stage -> stage_run.id），用于节点完成时关闭阶段。
        active_stages: dict[str, str] = {}
        # 通过 contextvar 把 run_id 注入日志与可观测性上下文。
        run_token = current_run_id.set(run_id)
        try:
            async for mode, payload in stream:
                # custom 事件：由图内显式发出，承载阶段开始等控制信息。
                if mode == "custom":
                    await self._handle_custom(run_id, payload, active_stages)
                    continue
                # 仅处理节点更新（updates）且其 payload 为字典，其余事件忽略。
                if mode != "updates" or not isinstance(payload, dict):
                    continue
                # 图中出现中断标记，说明需要人工审核，进入等待审核收尾。
                if "__interrupt__" in payload:
                    await self._mark_waiting_review(run_id, accumulated)
                    return
                for node, delta in payload.items():
                    if not isinstance(delta, dict):
                        continue
                    if node == "tools":
                        # 调试辅助：将 tools 节点的增量键打印到标准错误。
                        import sys
                        print(f"[DEBUG] tools delta keys: {list(delta.keys())}", file=sys.stderr, flush=True)
                    # 把本次节点增量并入全量状态，供后续阶段与产物引用。
                    accumulated.update(delta)
                    await self._persist_node_update(run_id, node, delta, accumulated, active_stages)
            # 事件流正常结束，标记为运行完成。
            await self._complete(run_id, accumulated)
        except Exception as error:
            # 任何未捕获异常都转为「运行失败」终态。
            await self._fail(run_id, error)
        finally:
            # 恢复 run_id contextvar，避免污染后续协程。
            current_run_id.reset(run_token)

    async def _handle_custom(self, run_id: str, payload: Any, active_stages: dict[str, str]) -> None:
        """处理 custom 事件：仅关注 stage.started，用于登记/切换当前阶段。

        首次出现某阶段时创建对应的 stage_run 并记录，后续重复到达仅更新映射。
        """
        if not isinstance(payload, dict):
            return
        if str(payload.get("type", "")).startswith("final_answer."):
            # Token 增量不落库，直接交给当前 SSE 订阅者；最终结果由 Run 快照持久化。
            run_live_event_broker.publish_transient(run_id, payload)
            return
        # 其他 custom 事件目前只处理阶段开始。
        if payload.get("type") != "stage.started":
            return
        stage = str(payload.get("stage") or "unknown")
        message = str(payload.get("message") or "正在处理")
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run or run.status == "cancelled":
                return
            # 同步运行级当前阶段字段，便于列表/详情直接展示进度。
            run.current_stage = stage
            await repository.save_run(run)
            # 查找是否已有同名的进行中阶段（幂等：重复起始事件不应重复建阶段）。
            stage_run = await repository.get_running_stage(run_id, stage)
            created = stage_run is None
            if created:
                stage_run = await repository.create_stage(run_id, stage, message)
            # 登记 stage_run.id，供节点完成时关闭阶段使用。
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
        """按节点类型把一次图更新（delta）翻译为落库产物与事件。

        这是执行器的核心分发逻辑：根据 node 名称与 delta 中的键，分别处理
        智能体决策、工具调用结果、检索/知识/计划/SQL 预览与执行、最终分析等，
        并在方法末尾关闭对应的运行阶段（stage）。
        """
        # 当前节点即对应一个阶段（阶段名与节点名一致）。
        stage = node
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run or run.status == "cancelled":
                return
            # 若规划节点产出了上下文化问题，回写运行记录供展示。
            if delta.get("contextualized_query"):
                run.contextualized_question = str(delta["contextualized_query"])
            run.current_stage = stage
            await repository.save_run(run)

            if node == "agent_decide" and delta.get("agent_decision"):
                # 智能体决策：登记其发出的工具调用并广播决策事件。
                decision = delta["agent_decision"]
                for message in delta.get("messages", []):
                    if not isinstance(message, AIMessage):
                        continue
                    for call in message.tool_calls:
                        await repository.start_tool_call(
                            conversation_id=run.conversation_id,
                            run_id=run.id,
                            tool_call_id=str(call["id"]),
                            tool_name=str(call["name"]),
                            arguments=_json_safe(call.get("args") or {}),
                        )
                await self._event(
                    repository,
                    run,
                    "agent.decision",
                    node,
                    {
                        "action": decision.get("action"),
                        "reasonSummary": decision.get("reasonSummary", ""),
                        "iteration": state.get("agent_iterations", 0),
                    },
                )
            elif node in {"tools", "sql_execute"}:
                # 工具/SQL 执行节点：完成工具调用记录并广播工具完成事件。
                if node == "tools":
                    for message in delta.get("messages", []):
                        if not isinstance(message, ToolMessage):
                            continue
                        content = str(message.content or "")
                        # 工具结果优先按 JSON 解析，失败则按原始文本保存。
                        try:
                            result = json.loads(content)
                        except json.JSONDecodeError:
                            result = content
                        await repository.complete_tool_call(
                            run_id=run.id,
                            tool_call_id=message.tool_call_id,
                            result=_json_safe(result),
                        )
                observations = delta.get("observations", [])
                # 取最近一条观察作为本次工具事件的简要信息。
                latest = observations[-1] if observations else {}
                await self._event(
                    repository,
                    run,
                    "tool.completed",
                    node,
                    {
                        "tool": latest.get("tool", node),
                        "ok": latest.get("ok", True),
                        "summary": latest.get("summary", ""),
                    },
                )

            if delta.get("plan"):
                # 分析计划产物：补充选中表（若模型未提供则回退到状态中的选择）。
                plan = dict(delta["plan"])
                plan.setdefault("selected_tables", state.get("selected_tables", []))
                await self._artifact(repository, run, stage, "plan", "分析计划已生成", plan)

            if node == "tools" and delta.get("schema"):
                # 已读取真实库表结构：落库结构快照并派生「检索结果」产物。
                await self._artifact(
                    repository,
                    run,
                    stage,
                    "schema_snapshot",
                    "已读取真实数据库结构",
                    delta["schema"],
                )
                await self._persist_retrieval(repository, run, state)
            elif node == "tools" and delta.get("knowledge") is not None:
                # 业务知识召回产物，摘要中附带文档+证据条数。
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
            elif node == "tools" and delta.get("python_analysis") is not None:
                # 调试辅助：输出 python_analysis 的增量信息到标准错误。
                import sys
                print(f"[DEBUG] python_analysis delta: keys={list(delta.keys())}, has result={bool(delta['python_analysis'].get('result'))}", file=sys.stderr, flush=True)
                python_analysis = delta["python_analysis"]
                result = python_analysis.get("result", {})
                await self._artifact(
                    repository,
                    run,
                    "python_analysis",
                    "python_analysis",
                    str(result.get("summary") or "Python 数据分析完成"),
                    python_analysis,
                )
            elif node == "sql_validate" and state.get("sql"):
                # SQL 校验通过后的查询预览产物（含安全性与查询范围）。
                await self._artifact(
                    repository,
                    run,
                    stage,
                    "query_preview",
                    "SQL 已生成并完成安全检查",
                    {
                        "sql": state["sql"],
                        # 依据安全检查结果标注当前查询状态。
                        "status": "validated" if state.get("safety", {}).get("passed") else "blocked",
                        "scope": {
                            "datasource": "sales-db",
                            "tables": state.get("selected_tables", []),
                            "timeRange": "由 SQL 条件确定",
                        },
                        "safety": state.get("safety", {}),
                    },
                )
            elif node == "sql_execute":
                # SQL 执行节点：根据是否存在 sql_error 分流到成功/失败落库。
                if delta.get("sql_error"):
                    await self._persist_query_failure(repository, run, state)
                else:
                    await self._persist_query_result(repository, run, state)
            elif node == "result" and delta.get("analysis"):
                # 最终分析结果产物：先做来源归一化，再写入并生成助手消息。
                analysis = _json_safe(delta["analysis"])
                queries = await repository.list_queries(run.id)
                # 收集本次运行已有的结果集 ID，用于校验图表/指标来源的有效性。
                result_set_ids = [item.result_set_id for item in queries if item.result_set_id]
                _normalize_result_sources(analysis, result_set_ids)
                await self._artifact(
                    repository,
                    run,
                    "result",
                    "analysis",
                    str(analysis.get("title") or "分析结果"),
                    analysis,
                )
                summary = str(analysis.get("summary") or "")
                if summary:
                    # 把分析摘要作为助手消息追加到会话，便于对话流展示。
                    await repository.add_message(
                        conversation_id=run.conversation_id,
                        run_id=run.id,
                        role="assistant",
                        content=summary,
                    )
                    await self._event(repository, run, "text.delta", "result", {"text": summary})

            # 关闭当前节点对应的阶段：优先用 active_stages 中的 id，否则回查进行中阶段。
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
        """生成「检索结果」产物：仅保留本次选中的表及其外键关系。

        从已读取的 schema 中按 selected_tables 过滤，并派生表间关系（外键），
        同时附上召回的业务知识（documents / evidences）。
        """
        # 仅保留被智能体选中的表，避免把无关表暴露给前端。
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
                    # 优先使用模型给出选中理由，否则给出默认理由。
                    "reason": state.get("schema_reasons", {}).get(table.get("name"), "与当前问题相关"),
                    "columns": table.get("columns", []),
                }
            )
            # 遍历外键，构造表与表之间的列级关系用于后续可视化。
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
        """落库一次成功的 SQL 查询：写入查询记录、结果历史并生成查询产物。"""
        # 取本次执行产生的最新查询结果（含 datasetId）。
        latest = state.get("query_results", [])[-1]
        result_set_id = latest.get("datasetId")
        result_set = await repository.get_result_set(result_set_id) if result_set_id else None
        if result_set is None:
            raise RuntimeError("SQL 查询完成但分析数据集不存在")
        # step_id 形如 step_01，序号由累计执行次数决定（至少 1）。
        query = await repository.add_query(
            run_id=run.id,
            step_id=f"step_{max(1, state.get('sql_execution_count', 1)):02d}",
            sql=state.get("sql", ""),
            status="success",
            attempt=state.get("retry_count", 0) + 1,
            duration_ms=None,
            row_count=result_set.total_rows,
            result_set_id=result_set.id,
            safety=state.get("safety", {}),
            error=None,
        )
        # 把结果集写入结果历史索引，供后续相似问题召回。
        await repository.index_result_history(
            run.conversation_id,
            run.id,
            result_set.id,
            run.contextualized_question or run.question,
            query.sql,
            [str(column.get("name") or "") for column in result_set.columns],
        )
        await self._artifact(
            repository,
            run,
            "sql_execute",
            "query",
            f"查询成功，返回 {result_set.total_rows} 行",
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
        # 回写结果集 ID 到状态，供后续分析产物引用。
        state["result_set_id"] = result_set.id

    async def _persist_query_failure(
        self,
        repository: Repository,
        run: AnalysisRunModel,
        state: dict[str, Any],
    ) -> None:
        """落库一次失败的 SQL 查询：写入失败查询记录与查询失败产物。"""
        query = await repository.add_query(
            run_id=run.id,
            step_id=f"step_{max(1, state.get('sql_execution_count', 1)):02d}",
            sql=state.get("sql", ""),
            status="failed",
            attempt=state.get("retry_count", 0) + 1,
            duration_ms=None,
            row_count=0,
            result_set_id=None,
            safety=state.get("safety", {}),
            error=state.get("sql_error"),
        )
        await self._artifact(
            repository,
            run,
            "sql_execute",
            "query",
            "SQL 执行失败，Agent 将根据错误决定下一步",
            {
                "id": query.id,
                "sql": query.sql,
                "status": query.status,
                "attempt": query.attempt,
                "rowCount": 0,
                "resultSetId": None,
                "safety": query.safety,
                "error": query.error,
            },
        )

    async def _artifact(
        self,
        repository: Repository,
        run: AnalysisRunModel,
        stage: str,
        artifact_type: str,
        summary: str,
        payload: dict[str, Any],
    ):
        """统一的产物落库入口：写入 artifact 并广播 artifact.created 事件。"""
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
        """图被人工审核中断时的收尾：创建审核记录并标记运行进入 waiting_review。"""
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run:
                return
            artifacts = await repository.list_artifacts(run_id)
            # 取最近一次的 plan 与 query_preview 产物作为审核上下文。
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
        """运行正常完成的收尾：标记终态、结算耗时并对行为类型做分类。"""
        async with session_factory() as session:
            repository = Repository(session)
            run = await repository.get_run(run_id)
            if not run or run.status == "cancelled":
                return
            run.status = "completed"
            # result_mode 优先取图内声明的结果模式，缺省视为成功。
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
            # 依据本次运行使用过的工具集合推断行为类别，用于统计与路由。
            tool_names = {item.tool_name for item in await repository.list_tool_calls(run.id)}
            if "rewrite_core_memory" in tool_names:
                behavior = "MEMORY_MANAGEMENT"
            elif tool_names & {"execute_sql", "analyze_dataframe", "search_schema", "retrieve_knowledge"}:
                behavior = "DATA_ANALYSIS"
            elif tool_names & {"search_conversation_history", "read_conversation_history"}:
                behavior = "HISTORY_QUERY"
            else:
                behavior = "CONVERSATION"
            await self._event(
                repository,
                run,
                "run.behavior_classified",
                "result",
                {"behavior": behavior},
            )
        # 图已经完整结束，展示与审计数据均已落入 app.db，此时 checkpoint 不再承担恢复职责。
        try:
            await self.runtime.delete_checkpoints([run_id])
            logger.info("completed run checkpoints deleted: runId=%s", run_id)
        except Exception:
            # 不把已成功的分析改写为 failed；定时清理会重试，异常必须留在日志中。
            logger.exception("completed run checkpoint cleanup failed: runId=%s", run_id)

    async def _fail(self, run_id: str, error: Exception) -> None:
        """运行异常失败的收尾：标记失败终态、结算耗时并补全未决调用/阶段。"""
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
            # 把运行期间仍未完成的工具调用标记为失败，避免悬挂的 pending 状态。
            for call in await repository.list_tool_calls(run.id):
                if call.status == "pending":
                    await repository.fail_tool_call(
                        run_id=run.id,
                        tool_call_id=call.tool_call_id,
                        error={"type": run.error_code, "message": run.error_message},
                    )
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
        """统一的领域事件落库入口：写入事件表，供前端 SSE/轮询订阅。"""
        event = await repository.add_event(
            run_id=run.id,
            conversation_id=run.conversation_id,
            event_type=event_type,
            stage=stage,
            data=_json_safe(data),
        )
        # 必须在事务提交成功后广播，保证客户端收到的持久事件一定可以从 SQLite 补发。
        run_live_event_broker.publish_persistent(event)


def _json_safe(value: Any) -> Any:
    """把任意可序列化对象（含非 JSON 原生类型）转为 JSON 兼容结构。

    通过默认序列化再解析的方式，确保下游持久化与事件数据均为纯 JSON 类型。
    """
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _stage_message(node: str, delta: dict[str, Any]) -> str:
    """根据节点名返回该阶段完成时的中文提示文案。

    sql_execute 节点会依据 delta 中是否存在 sql_error 区分成功/失败文案。
    """
    messages = {
        "input_guard": "请求安全检查完成",
        "agent_decide": "下一步分析动作已确定",
        "agent_schema_search": "相关数据表检索完成",
        "agent_schema_inspect": "数据表结构读取完成",
        "agent_knowledge_search": "业务知识检索完成",
        "tools": "工具调用完成",
        "knowledge_recall": "业务知识召回完成",
        "schema_recall": "数据库结构读取完成",
        "planner": "分析计划已生成",
        "simple_plan": "单步执行方案已准备",
        "sql_generate": "SQL 已生成",
        "sql_validate": "SQL 安全检查完成",
        "human_feedback": "人工审核完成",
        "sql_execute": "SQL 执行完成" if not delta.get("sql_error") else "SQL 执行失败，准备修复",
        "result": "分析结果已生成",
    }
    return messages.get(node, f"{node} 已完成")


def _normalize_result_sources(analysis: dict[str, Any], result_set_ids: list[str]) -> None:
    """保证分析结果中图表/指标/发现的来源（resultSetId）均为本运行合法的结果集。

    仅当本运行恰好只有一个结果集时，才把未显式声明或声明非法的来源推断为该结果集；
    否则只保留有效来源，缺失来源时不影响其余数据。
    """
    valid_ids = set(result_set_ids)
    fallback = result_set_ids[0] if len(result_set_ids) == 1 else ""
    for chart in analysis.get("charts", []):
        source = chart.get("resultSetId")
        chart["resultSetId"] = source if source in valid_ids else fallback
    for metric in analysis.get("metrics", []):
        source = metric.get("sourceResultSetId")
        metric["sourceResultSetId"] = source if source in valid_ids else fallback
    for finding in analysis.get("findings", []):
        sources = finding.get("sourceResultSetIds") or []
        finding["sourceResultSetIds"] = [source for source in sources if source in valid_ids]
        if not finding["sourceResultSetIds"] and fallback:
            finding["sourceResultSetIds"] = [fallback]


# 模块级单例：基于全局配置构建运行时与执行器，供命令/控制服务直接引用。
settings = get_settings()
graph_runtime = GraphRuntime(settings)
workflow = GraphAnalysisExecutor(graph_runtime)
