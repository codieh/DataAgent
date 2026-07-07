# Agent Context and Tool Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single model-facing context projection, remove duplicated Schema/SQL rows, and let the Agent search and inspect durable historical query results safely.

**Architecture:** Durable conversations, runs, queries, result sets, and full traces remain the source of truth. A new `AgentContextBuilder` projects only bounded current facts and compact protocol messages into each LLM request; historical result metadata is searched through SQLite FTS5 and rows are loaded on demand by `datasetId`.

**Tech Stack:** Python 3.13, LangGraph, LangChain Core tools/messages, SQLAlchemy async, SQLite/FTS5, CSV-backed `AnalysisDatasetStore`, pytest.

## Global Constraints

- The effective model context limit remains exactly `200_000` tokens.
- Never split an assistant tool call from its matching `ToolMessage` in the model-facing projection.
- Full persisted traces and result sets are not deleted when model-facing content is compacted.
- Every historical search and result read is restricted to the active `conversation_id`.
- A model request contains a complete Schema at most once and the same SQL rows at most once.
- No automatic SQL re-execution is added for missing or expired result sets.

---

## File Structure

- Create `app/analysis/history.py`: conversation-scoped history catalog, FTS search, and result inspection service.
- Create `app/workflow/context_builder.py`: the only builder for Agent payloads and projected Tool Messages.
- Modify `app/infrastructure/persistence/database.py`: create the SQLite FTS5 table during database initialization.
- Modify `app/infrastructure/persistence/repositories/artifacts.py`: index, list, search, authorize, and delete result-history records.
- Modify `app/infrastructure/persistence/repositories/conversations.py`: clean FTS rows when deleting a conversation.
- Modify `app/application/executor.py`: index successful query results and keep persisted artifacts intact.
- Modify `app/workflow/tools.py`: register `search_history` and `inspect_query_result`; compact Schema observations.
- Modify `app/workflow/nodes/analysis.py`: delegate model input assembly and remove duplicated result fields.
- Modify `app/workflow/state.py`: make result references explicit while retaining compatibility fields only where the UI still consumes them.
- Modify `app/workflow/graph.py` and `app/workflow/runtime.py`: wire history and context dependencies.
- Modify `app/config.py`: add fixed budgets and limits for result catalogs, previews, and tool projection.
- Create `tests/test_result_history.py`: persistence, authorization, FTS, fallback, and paging tests.
- Create `tests/test_agent_context.py`: deduplication, protocol pairing, and budget tests.
- Modify `tests/test_retrieval.py`: native tool schema tests for the two new tools.
- Modify `tests/test_api.py`: cross-turn historical-result reuse regression.

---

### Task 1: Durable Result History Search

**Files:**
- Create: `data-agent-python-backend/app/analysis/history.py`
- Modify: `data-agent-python-backend/app/infrastructure/persistence/database.py`
- Modify: `data-agent-python-backend/app/infrastructure/persistence/repositories/artifacts.py`
- Modify: `data-agent-python-backend/app/infrastructure/persistence/repositories/conversations.py`
- Modify: `data-agent-python-backend/app/application/executor.py`
- Test: `data-agent-python-backend/tests/test_result_history.py`

**Interfaces:**
- Produces: `ResultHistoryService.recent(conversation_id: str, limit: int) -> list[dict[str, Any]]`
- Produces: `ResultHistoryService.search(conversation_id: str, query: str, scope: str, limit: int) -> list[dict[str, Any]]`
- Produces: `ResultHistoryService.inspect(conversation_id: str, dataset_id: str, offset: int, limit: int) -> dict[str, Any]`
- Produces: `Repository.index_result_history(...)`, `Repository.search_result_history(...)`, and `Repository.get_conversation_result_set(...)`.

- [ ] **Step 1: Write failing repository and service tests**

Add tests that create two conversations with result sets and assert search and inspection never cross the conversation boundary:

```python
@pytest.mark.asyncio
async def test_result_history_search_and_inspect_are_conversation_scoped(database_session, settings):
    first = await seed_result(database_session, conversation_id="conv_a", question="各省销售额", rows=[{"province": "浙江", "sales": 10}])
    await seed_result(database_session, conversation_id="conv_b", question="各省销售额", rows=[{"province": "江苏", "sales": 99}])
    service = ResultHistoryService(settings)

    matches = await service.search("conv_a", "省 销售额", "query_results", 5)
    inspected = await service.inspect("conv_a", first.id, 0, 20)

    assert [item["datasetId"] for item in matches] == [first.id]
    assert inspected["rows"] == [{"province": "浙江", "sales": 10}]
    with pytest.raises(ResourceNotFoundError):
        await service.inspect("conv_a", "result_owned_by_conv_b", 0, 20)
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `cd data-agent-python-backend && .venv/bin/pytest tests/test_result_history.py -q`

Expected: FAIL because `ResultHistoryService` and history repository methods do not exist.

- [ ] **Step 3: Create FTS5 storage during initialization**

After `Base.metadata.create_all`, execute SQLite-only DDL:

```python
await connection.exec_driver_sql(
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS result_history_fts USING fts5(
        dataset_id UNINDEXED,
        conversation_id UNINDEXED,
        run_id UNINDEXED,
        question,
        sql,
        columns,
        summary,
        tokenize='unicode61'
    )
    """
)
```

For non-SQLite databases, repository search must use the structured `LIKE` fallback and must not execute SQLite DDL.

- [ ] **Step 4: Implement repository indexing and authorization**

Add exact repository operations:

```python
async def get_conversation_result_set(self, conversation_id: str, result_set_id: str) -> ResultSetModel | None:
    statement = (
        select(ResultSetModel)
        .join(AnalysisRunModel, AnalysisRunModel.id == ResultSetModel.run_id)
        .where(ResultSetModel.id == result_set_id, AnalysisRunModel.conversation_id == conversation_id)
    )
    return await self.session.scalar(statement)

async def index_result_history(self, *, dataset_id: str, conversation_id: str, run_id: str,
                               question: str, sql: str, columns: list[dict[str, Any]], summary: str = "") -> None:
    await self.session.execute(text("DELETE FROM result_history_fts WHERE dataset_id = :dataset_id"), {"dataset_id": dataset_id})
    await self.session.execute(text("""INSERT INTO result_history_fts
        (dataset_id, conversation_id, run_id, question, sql, columns, summary)
        VALUES (:dataset_id, :conversation_id, :run_id, :question, :sql, :columns, :summary)"""),
        {"dataset_id": dataset_id, "conversation_id": conversation_id, "run_id": run_id,
         "question": question, "sql": sql, "columns": " ".join(c.get("name", "") for c in columns),
         "summary": summary})
    await self.session.commit()
```

Escape FTS input into quoted terms; if no usable term remains or FTS raises `OperationalError`, use a joined Query/Run/ResultSet `LIKE` query scoped by conversation.

- [ ] **Step 5: Implement `ResultHistoryService`**

Use `session_factory`, `Repository`, and `AnalysisDatasetStore`. Enforce `limit <= 10` for search and `limit <= 50` for inspection. Return:

```python
{
    "datasetId": result_set.id,
    "columns": result_set.columns,
    "rows": rows,
    "rowCount": result_set.total_rows,
    "offset": offset,
    "returnedRows": len(rows),
    "hasMore": offset + len(rows) < result_set.total_rows,
    "truncated": result_set.truncated,
}
```

- [ ] **Step 6: Index successful queries and clean deleted conversations**

Immediately after `_persist_query_result` creates `QueryModel`, call `index_result_history` with `run.question`, SQL, columns, and `datasetId`. In `delete_conversation`, delete matching FTS rows before deleting the conversation. Do not index failed SQL.

- [ ] **Step 7: Run focused tests**

Run: `cd data-agent-python-backend && .venv/bin/pytest tests/test_result_history.py -q`

Expected: all result-history tests PASS, including FTS search, fallback search, pagination, expired-CSV preview fallback, and cross-conversation denial.

- [ ] **Step 8: Commit**

```bash
git add data-agent-python-backend/app/analysis/history.py \
  data-agent-python-backend/app/infrastructure/persistence/database.py \
  data-agent-python-backend/app/infrastructure/persistence/repositories/artifacts.py \
  data-agent-python-backend/app/infrastructure/persistence/repositories/conversations.py \
  data-agent-python-backend/app/application/executor.py \
  data-agent-python-backend/tests/test_result_history.py
git commit -m "feat: add conversation result history search"
```

---

### Task 2: Single Agent Context Projection

**Files:**
- Create: `data-agent-python-backend/app/workflow/context_builder.py`
- Modify: `data-agent-python-backend/app/config.py`
- Test: `data-agent-python-backend/tests/test_agent_context.py`

**Interfaces:**
- Consumes: `ResultHistoryService.recent(...)` from Task 1.
- Produces: `AgentContextBuilder.build(state: AnalysisState) -> AgentContext`, where `AgentContext.payload` is JSON-serializable and `AgentContext.messages` preserves valid tool protocol pairs.

- [ ] **Step 1: Write failing projection tests**

Construct state containing the same sentinel in Schema, observation, ToolMessage, `query_results`, `rows`, and `lastResult`-equivalent data. Assert the serialized model projection contains Schema sentinel once and row sentinel once:

```python
context = await builder.build(state)
serialized = json.dumps({"payload": context.payload, "messages": serialize(context.messages)}, ensure_ascii=False)
assert serialized.count("UNIQUE_SCHEMA_SENTINEL") == 1
assert serialized.count("UNIQUE_ROW_SENTINEL") == 1
assert_tool_pairs_are_complete(context.messages)
```

Also test that old large ToolMessages become compact references while the latest useful result remains available.

- [ ] **Step 2: Run tests and verify failure**

Run: `cd data-agent-python-backend && .venv/bin/pytest tests/test_agent_context.py -q`

Expected: FAIL because `AgentContextBuilder` does not exist.

- [ ] **Step 3: Add explicit projection limits**

Add settings with these defaults:

```python
context_result_catalog_limit: int = 5
context_result_preview_rows: int = 20
context_history_search_limit: int = 5
context_tool_result_keep_recent: int = 1
context_tool_result_compact_chars: int = 2_000
```

Validate all values are positive and keep `max_context_size=200_000` unchanged.

- [ ] **Step 4: Implement model payload construction**

Build exactly these top-level keys:

```python
payload = {
    "query": state.get("contextualized_query") or state["query"],
    "memory": supplemental_memory(state),
    "plan": state.get("plan"),
    "iteration": iteration + 1,
    "budgets": build_agent_budgets(state, settings),
    "schema": budget_schema(state.get("schema", {}), settings.context_schema_token_budget),
    "knowledge": budget_knowledge(state.get("knowledge", {}), settings.context_knowledge_token_budget),
    "activeResult": await active_result_preview(state),
    "availableResults": await history.recent(state["conversation_id"], settings.context_result_catalog_limit),
    "observations": compact_observations(state.get("observations", [])[-8:]),
    "pythonAnalyses": [item.get("result", {}) for item in state.get("python_analyses", [])],
}
```

Exclude the active `datasetId` from `availableResults`. Remove `queryResults` and `lastResult` from model payloads.

- [ ] **Step 5: Implement Tool Message projection**

Walk assistant/tool messages as protocol groups. Keep the latest configured data-bearing result; replace older oversized tool content with JSON such as:

```json
{"ok":true,"compacted":true,"datasetId":"result_123","summary":"历史工具结果已归档，可按结果编号重新读取"}
```

For Schema results, retain only `ok`, `summary`, `tableNames`, and `schemaRef`. Never mutate `state["messages"]`.

- [ ] **Step 6: Run focused tests**

Run: `cd data-agent-python-backend && .venv/bin/pytest tests/test_agent_context.py -q`

Expected: all projection, deduplication, immutability, budget, and protocol-pair tests PASS.

- [ ] **Step 7: Commit**

```bash
git add data-agent-python-backend/app/workflow/context_builder.py \
  data-agent-python-backend/app/config.py \
  data-agent-python-backend/tests/test_agent_context.py
git commit -m "feat: add bounded agent context projection"
```

---

### Task 3: Native Historical Result Tools

**Files:**
- Modify: `data-agent-python-backend/app/workflow/tools.py`
- Modify: `data-agent-python-backend/app/workflow/prompts.py`
- Modify: `data-agent-python-backend/tests/test_retrieval.py`
- Test: `data-agent-python-backend/tests/test_result_history.py`

**Interfaces:**
- Consumes: `ResultHistoryService` from Task 1.
- Produces native tools `search_history(query: str, scope: str = "all", limit: int = 5)` and `inspect_query_result(dataset_id: str, offset: int = 0, limit: int = 20)`.

- [ ] **Step 1: Extend failing tool-schema tests**

```python
assert set(specifications["search_history"]["properties"]) == {"query", "scope", "limit"}
assert set(specifications["inspect_query_result"]["properties"]) == {"dataset_id", "offset", "limit"}
```

Invoke both tools with an injected state and assert the service receives `state["conversation_id"]`, never a model-supplied conversation ID.

- [ ] **Step 2: Run tests and verify failure**

Run: `cd data-agent-python-backend && .venv/bin/pytest tests/test_retrieval.py tests/test_result_history.py -q`

Expected: FAIL because the tools are not registered.

- [ ] **Step 3: Register `search_history`**

The tool validates `scope in {"query_results", "analyses", "all"}` and clamps `limit` to `1..10`. Its ToolMessage contains only match metadata and no rows.

- [ ] **Step 4: Register `inspect_query_result`**

The tool clamps `offset >= 0` and `limit` to `1..50`, calls the scoped service, and returns rows only in its ToolMessage. Its observation contains only `datasetId`, `rowCount`, `returnedRows`, and summary.

- [ ] **Step 5: Compact Schema tools at the source**

Change `search_schema` and `inspect_tables` observations from full `tables` to:

```python
{
    "tool": "search_schema",
    "ok": bool(selected),
    "summary": f"召回 {len(selected)} 张候选表",
    "tableNames": selected,
    "schemaRef": "state.schema",
}
```

The actual Schema remains in `state.schema`.

- [ ] **Step 6: Clarify tool-selection instructions**

Add concise prompt rules: use `availableResults` for an unambiguous recent reference; use `search_history` when the referenced result is old or ambiguous; use `inspect_query_result` only after choosing a `datasetId`.

- [ ] **Step 7: Run focused tests**

Run: `cd data-agent-python-backend && .venv/bin/pytest tests/test_retrieval.py tests/test_result_history.py -q`

Expected: PASS with nine native tools and no exposed `state`, `conversation_id`, or `tool_call_id` arguments.

- [ ] **Step 8: Commit**

```bash
git add data-agent-python-backend/app/workflow/tools.py \
  data-agent-python-backend/app/workflow/prompts.py \
  data-agent-python-backend/tests/test_retrieval.py \
  data-agent-python-backend/tests/test_result_history.py
git commit -m "feat: add historical result agent tools"
```

---

### Task 4: Integrate Projection and Remove Duplicate Runtime Data

**Files:**
- Modify: `data-agent-python-backend/app/workflow/nodes/analysis.py`
- Modify: `data-agent-python-backend/app/workflow/state.py`
- Modify: `data-agent-python-backend/app/workflow/graph.py`
- Modify: `data-agent-python-backend/app/workflow/runtime.py`
- Modify: `data-agent-python-backend/app/application/executor.py`
- Test: `data-agent-python-backend/tests/test_agent_context.py`
- Modify: `data-agent-python-backend/tests/test_api.py`

**Interfaces:**
- Consumes: `AgentContextBuilder` and `ResultHistoryService`.
- Produces: Agent decisions using one projected payload and current result references shaped as `{datasetId, sql, columns, rowCount}`.

- [ ] **Step 1: Write failing integration tests**

Capture the messages passed to `complete_tool_messages` and assert they contain no `lastResult`, no result rows inside observations, and no Schema tables inside ToolMessages. Add an API regression where turn two references turn one's result and the fake LLM selects history tools.

- [ ] **Step 2: Run tests and verify failure**

Run: `cd data-agent-python-backend && .venv/bin/pytest tests/test_agent_context.py tests/test_api.py -q`

Expected: FAIL on current duplicate payload construction.

- [ ] **Step 3: Delegate `agent_decide` assembly**

Replace the inline payload in `agent_decide` with:

```python
context = await self.agent_context_builder.build(state)
response = await self.llm.complete_tool_messages(
    AGENT_SYSTEM,
    context.messages,
    tools=self.tool_registry.specifications(),
)
```

Keep routing limits and action correction unchanged.

- [ ] **Step 4: Store SQL result references, not repeated previews**

After SQL execution, append:

```python
result_ref = {
    "datasetId": dataset["id"],
    "sql": state["sql"],
    "columns": columns,
    "rowCount": len(rows),
}
```

The execution observation contains only `tool`, `ok`, `rowCount`, `datasetId`, and summary. Keep `columns` and `rows` temporarily only if required by existing frontend persistence during this task, but never send them through `AgentContextBuilder`; remove compatibility fields after the API regression proves consumers use result sets.

- [ ] **Step 5: Make the result node read one preview by `datasetId`**

Load the latest result through `ResultHistoryService.inspect` and construct one result payload. Remove simultaneous `rows` plus `query_results[].rows` serialization.

- [ ] **Step 6: Wire dependencies once**

`GraphRuntime` owns one `ResultHistoryService` and one `AgentContextBuilder`. Pass both through `build_analysis_graph` into `AnalysisNodes` and `AnalysisToolRegistry`; do not instantiate services per node call.

- [ ] **Step 7: Run focused and full tests**

Run: `cd data-agent-python-backend && .venv/bin/pytest tests/test_agent_context.py tests/test_api.py -q`

Expected: focused integration tests PASS.

Run: `cd data-agent-python-backend && .venv/bin/pytest -q`

Expected: complete test suite PASS.

- [ ] **Step 8: Commit**

```bash
git add data-agent-python-backend/app/workflow/nodes/analysis.py \
  data-agent-python-backend/app/workflow/state.py \
  data-agent-python-backend/app/workflow/graph.py \
  data-agent-python-backend/app/workflow/runtime.py \
  data-agent-python-backend/app/application/executor.py \
  data-agent-python-backend/tests/test_agent_context.py \
  data-agent-python-backend/tests/test_api.py
git commit -m "refactor: project agent context from durable state"
```

---

### Task 5: Regression, Observability, and Documentation

**Files:**
- Modify: `data-agent-python-backend/app/application/executor.py`
- Modify: `data-agent-python-backend/README.md`
- Modify: `docs/python-backend-message-assembly.md`
- Test: `data-agent-python-backend/tests/test_agent_context.py`

**Interfaces:**
- Consumes all earlier tasks.
- Produces prompt-size diagnostics and current architecture documentation.

- [ ] **Step 1: Add projection statistics tests**

Assert `AgentContextBuilder` reports estimated tokens, Schema tokens, active-result rows, history catalog count, compacted ToolMessage count, and final serialized characters without logging row contents.

- [ ] **Step 2: Add safe diagnostics**

Log one structured line before Agent LLM calls:

```text
agent context built: runId=... estimatedTokens=... schemaTokens=... activeResultRows=...
historyResults=... toolMessages=... compactedToolMessages=...
```

Do not log SQL result rows or sensitive column values.

- [ ] **Step 3: Update documentation**

Document the four boundaries, `search_history -> inspect_query_result` flow, ToolMessage compaction, and the exact reason full persisted history differs from model-visible history. Remove the obsolete diagram showing duplicate Schema and SQL rows as intended behavior.

- [ ] **Step 4: Run verification**

Run: `cd data-agent-python-backend && .venv/bin/pytest -q`

Expected: all tests PASS.

Run: `cd data-agent-python-backend && .venv/bin/python -m compileall -q app tests`

Expected: exit code 0 with no syntax errors.

Run: `cd data-agent-python-backend && .venv/bin/ruff check app tests`

Expected: exit code 0 with no lint errors.

- [ ] **Step 5: Inspect the final diff**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intended source, test, and documentation files are changed in this implementation series, while pre-existing unrelated worktree changes remain untouched.

- [ ] **Step 6: Commit**

```bash
git add data-agent-python-backend/app/application/executor.py \
  data-agent-python-backend/README.md \
  docs/python-backend-message-assembly.md \
  data-agent-python-backend/tests/test_agent_context.py
git commit -m "docs: explain agent context and history retrieval"
```
