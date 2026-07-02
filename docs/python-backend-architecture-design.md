# DataAgent Python 后端重构设计

> 状态：Approved v1，实施中  
> 日期：2026-07-01  
> 适用范围：`data-agent-frontend` 对应的新 Python 后端  
> 目标：先完整满足现有前端的数据与交互需求，再逐步增强 Agent 能力。

## 1. 背景

当前前端已经具备欢迎页、会话工作区、执行过程、结果页、人工审核和设置页等完整产品形态，但其中大量数据仍是静态示例：

- 历史会话、推荐问题和 Agent 列表是静态数据。
- 工作区中的召回表、阶段耗时、行数和 SQL 示例是静态数据。
- 结果页中的标题、总结、关键发现、指标、图表、表格和分析依据是静态数据。
- 人工审核页中的计划、SQL、查询范围和安全说明是静态数据。
- 当前后端虽然能够产生部分 SQL、结果行、召回结果和总结，但通过松散的 SSE `payload` 分阶段返回，没有形成前端可以稳定消费的完整运行结果。

本次重构不按照现有 Java 类逐一翻译，而是以前端所需的数据契约为起点重新设计 Python 后端。

## 2. 设计目标

### 2.1 第一阶段目标

1. 用真实后端数据替换当前前端的静态分析数据。
2. 支持新建会话、多轮追问、历史恢复、重命名、搜索和删除。
3. 支持实时展示执行阶段、进度、耗时、SQL、结果和错误。
4. 支持结果页展示总结、关键发现、指标、图表、表格、SQL 和分析依据。
5. 支持人工审核暂停、批准、退回和恢复执行。
6. 支持取消、重试、断线恢复和结果重新加载。
7. 使用 SQLite 保存应用状态，较大结果保存为本地文件。
8. 保持接口稳定，使内部工作流后续可以演进而不影响前端。

### 2.2 非目标

第一阶段不实现：

- 多 Agent 协作或 Agent 群聊。
- 开放式、无边界的 ReAct 循环。
- 任意 Python 代码生成与本地执行。
- Skill 市场或复杂 Skill 管理。
- 用户注册、组织、计费和多租户权限。
- 云端会话同步。
- 生产级分布式任务调度。

这些能力只能在有明确需求和评测收益后加入。

## 3. 核心原则

### 3.1 数据库是事实来源

SSE 只负责通知状态变化，不是最终数据来源。`AnalysisRun` 的持久化快照才是一次分析的最终事实。

### 3.2 REST 与 SSE 分工

- REST：创建、查询、修改、分页、下载和恢复完整数据。
- SSE：阶段状态、流式文本、轻量进度、产物通知和终态通知。

### 3.3 固定主流程，局部受控循环

外层流程保持可预测；复杂任务允许有限次分析循环，SQL 失败允许有限次修复。所有循环都必须有次数、时间和 Token 上限。

### 3.4 LLM 不负责确定性安全

LLM 可以识别风险和提出建议，但 SQL 是否允许执行必须由确定性代码决定。

### 3.5 前端不依赖工作流内部状态

LangGraph State、Checkpoint 数据和节点内部字段不得直接成为 API DTO。前端只依赖版本化的 API 模型和事件协议。

### 3.6 大数据不进入模型上下文和 SSE

业务数据库负责过滤和聚合，结果集通过分页或文件访问；LLM 只接收必要的统计摘要和少量样本。

## 4. 总体架构

```text
Electron + React
├── REST：持久化数据、完整结果、分页与操作
└── SSE：运行过程、文本增量和状态通知
              │
              ▼
FastAPI
├── Bootstrap / Health API
├── Conversation API
├── Analysis Run API
├── Result / Artifact API
├── Review API
└── SSE Event API
              │
              ▼
Application Services
├── ConversationService
├── AnalysisRunService
├── ResultService
├── ReviewService
└── EventService
              │
              ▼
LangGraph Workflow
├── 上下文准备
├── 意图识别
├── Schema 与知识召回
├── 查询补全
├── 分析规划
├── 受控分析循环
├── SQL 生成与安全检查
├── SQL 执行与修复
├── 人工审核
└── 结构化结果总结
              │
              ▼
Infrastructure
├── SQLite
├── 本地 Parquet / 导出文件
├── 业务数据库连接器
├── pgvector / 检索实现
├── LLM Provider
└── LangGraph Checkpointer
```

## 5. Python 工程结构

```text
backend/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   ├── schemas/
│   │   └── dependencies.py
│   ├── application/
│   │   ├── conversations.py
│   │   ├── runs.py
│   │   ├── results.py
│   │   └── reviews.py
│   ├── domain/
│   │   ├── conversation.py
│   │   ├── run.py
│   │   ├── artifact.py
│   │   └── review.py
│   ├── workflow/
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes/
│   │   └── routing.py
│   ├── retrieval/
│   │   ├── schema/
│   │   ├── document/
│   │   ├── bm25.py
│   │   ├── vector.py
│   │   ├── fusion.py
│   │   └── reranker.py
│   ├── sql/
│   │   ├── generator.py
│   │   ├── policy.py
│   │   ├── executor.py
│   │   └── repair.py
│   ├── analysis/
│   │   ├── summarizer.py
│   │   ├── chart_builder.py
│   │   └── operations/
│   ├── infrastructure/
│   │   ├── database/
│   │   ├── persistence/
│   │   ├── llm/
│   │   ├── files/
│   │   └── events/
│   └── eval/
├── migrations/
├── data/
│   ├── results/
│   └── exports/
└── tests/
```

## 6. 前端需求与后端能力映射

| 前端区域 | 必需数据 | 后端能力 |
| --- | --- | --- |
| 欢迎页 | 推荐问题、服务状态、默认 Agent | Bootstrap API、Health API |
| 左侧会话栏 | 标题、更新时间、最后状态、搜索结果 | Conversation API |
| 对话工作区 | 用户消息、Agent 回复、当前运行状态 | Message、AnalysisRun、SSE |
| 执行过程 | 阶段、状态、说明、真实耗时、错误 | StageRun、SSE |
| 数据召回 | 表、字段、关系、文档、依据、分数 | Retrieval Artifact |
| 任务规划 | 计划步骤、当前步骤、步骤状态 | Plan Artifact |
| SQL 展示 | SQL、安全检查、执行状态、重试 | Query Artifact |
| 查询结果 | 列、行、总数、截断、分页 | ResultSet API |
| 结果页 | 标题、总结、发现、指标、图表 | Analysis Artifact |
| 人工审核 | 计划、SQL、范围、安全检查 | ReviewCheckpoint |
| 设置页 | Agent、数据源、健康检查 | Bootstrap、Datasource API |
| 开发者详情 | 原始事件、序号、时间戳、Payload | Run Event API |

以下内容由前端本地保存，不要求后端持久化：

- 界面缩放、主题和面板宽度。
- 侧栏折叠状态。
- 当前路由和临时输入草稿。
- 本地后端服务地址。

## 7. 核心领域模型

### 7.1 Conversation

```text
id
title
agent_id
datasource_id
summary
status
created_at
updated_at
last_run_id
```

### 7.2 Message

```text
id
conversation_id
run_id
role                 user / assistant / system
content
content_type         markdown / text
created_at
```

只保存用户输入和最终 Agent 回答。节点调试内容不混入对话消息。

### 7.3 AnalysisRun

```text
id
conversation_id
question
contextualized_question
status               queued / running / waiting_review / completed / failed / cancelled
result_mode
current_stage
started_at
completed_at
duration_ms
error_code
error_message
version
```

### 7.4 StageRun

```text
id
run_id
stage
attempt
status               pending / running / completed / failed / skipped
message
started_at
completed_at
duration_ms
error_code
error_message
```

### 7.5 Artifact

Artifact 表示工作流产生、可以被前端展示或被后续节点引用的结构化产物。

```text
id
run_id
stage
type
version
summary
payload_json
file_path
created_at
expires_at
```

第一阶段支持以下类型：

```text
retrieval
plan
query
result_set
analysis
chart
review
error_detail
```

### 7.6 ReviewCheckpoint

```text
id
run_id
status               waiting / approved / rejected / expired
plan_artifact_id
query_artifact_id
reason
review_comment
created_at
reviewed_at
```

## 8. AnalysisRun API 模型

`GET /api/v1/runs/{run_id}` 返回一次运行的完整快照：

```json
{
  "id": "run_01",
  "conversationId": "conv_01",
  "status": "completed",
  "resultMode": "success",
  "question": "分析最近30天销量变化",
  "contextualizedQuestion": "分析当前销售数据库最近30天销量变化",
  "currentStage": "result",
  "startedAt": "2026-07-01T10:00:00+08:00",
  "completedAt": "2026-07-01T10:00:12+08:00",
  "durationMs": 12680,
  "stages": [
    {
      "name": "schema_recall",
      "status": "completed",
      "message": "找到3张相关数据表",
      "durationMs": 1120
    }
  ],
  "retrieval": {
    "tables": [],
    "relations": [],
    "documents": [],
    "evidences": []
  },
  "plan": {
    "steps": []
  },
  "queries": [],
  "analysis": {
    "title": "近30天销量呈下降趋势",
    "summary": "Markdown summary",
    "findings": [],
    "metrics": [],
    "charts": []
  },
  "review": null,
  "error": null
}
```

## 9. Artifact 数据契约

### 9.1 Retrieval Artifact

```json
{
  "tables": [
    {
      "name": "orders",
      "displayName": "订单表",
      "score": 0.91,
      "reason": "包含订单日期、状态和金额",
      "columns": [
        {
          "name": "order_date",
          "dataType": "date",
          "description": "订单日期",
          "score": 0.88
        }
      ]
    }
  ],
  "relations": [
    {
      "fromTable": "orders",
      "fromColumn": "id",
      "toTable": "order_items",
      "toColumn": "order_id"
    }
  ],
  "documents": [],
  "evidences": []
}
```

### 9.2 Plan Artifact

```json
{
  "goal": "分析最近30天销量趋势并定位异常",
  "successCriteria": ["返回每日销量", "识别明显异常日期"],
  "steps": [
    {
      "id": "step_01",
      "index": 0,
      "title": "统计每日销量",
      "objective": "按日期聚合最近30天销量",
      "status": "completed",
      "queryArtifactIds": ["query_01"],
      "resultSetIds": ["result_01"]
    }
  ]
}
```

### 9.3 Query Artifact

```json
{
  "id": "query_01",
  "stepId": "step_01",
  "sql": "SELECT ...",
  "status": "success",
  "attempt": 1,
  "durationMs": 420,
  "rowCount": 30,
  "resultSetId": "result_01",
  "safety": {
    "passed": true,
    "readOnly": true,
    "limitApplied": true,
    "sensitiveFields": [],
    "checks": []
  },
  "error": null
}
```

### 9.4 ResultSet

```json
{
  "id": "result_01",
  "columns": [
    {
      "name": "order_date",
      "label": "日期",
      "dataType": "date"
    },
    {
      "name": "sales_count",
      "label": "销量",
      "dataType": "number"
    }
  ],
  "rows": [],
  "page": 1,
  "pageSize": 100,
  "returnedRows": 30,
  "totalRows": 30,
  "truncated": false
}
```

### 9.5 Analysis Artifact

```json
{
  "title": "近30天销量先升后降",
  "summary": "Markdown summary",
  "findings": [
    {
      "id": "finding_01",
      "title": "促销结束后销量下降",
      "description": "最近11天销量下降18.4%",
      "severity": "warning",
      "metricIds": ["metric_01"],
      "sourceResultSetIds": ["result_01"]
    }
  ],
  "metrics": [
    {
      "id": "metric_01",
      "label": "销量变化",
      "value": -18.4,
      "formattedValue": "-18.4%",
      "unit": "%",
      "description": "最近11天",
      "sourceResultSetId": "result_01"
    }
  ],
  "charts": []
}
```

### 9.6 Chart Artifact

后端只返回图表语义，不生成图片，也不复制整份结果数据。

```json
{
  "id": "chart_01",
  "type": "line",
  "title": "近30天销量趋势",
  "resultSetId": "result_01",
  "xField": "order_date",
  "yFields": ["sales_count"],
  "seriesField": null,
  "options": {
    "showLegend": false,
    "showDataZoom": false
  }
}
```

图表字段必须存在于引用的 ResultSet，后端在保存前完成校验。

## 10. REST API

### 10.1 初始化与健康检查

```text
GET /api/v1/bootstrap
GET /api/v1/health
```

`bootstrap` 返回：

- 默认 Agent。
- 可用 Agent Profile。
- 推荐问题。
- 可用数据源摘要。
- 前端功能开关。

### 10.2 会话

```text
POST   /api/v1/conversations
GET    /api/v1/conversations?q=&cursor=&limit=
GET    /api/v1/conversations/{conversation_id}
PATCH  /api/v1/conversations/{conversation_id}
DELETE /api/v1/conversations/{conversation_id}
```

会话详情包含消息列表和最近运行摘要，不默认加载全部 Artifact 和大结果集。

### 10.3 分析任务

```text
POST /api/v1/conversations/{conversation_id}/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/runs/{run_id}/events?after_seq=
POST /api/v1/runs/{run_id}/cancel
POST /api/v1/runs/{run_id}/retry
```

创建运行请求：

```json
{
  "query": "分析最近30天销量变化",
  "agentId": "default-analysis",
  "datasourceId": "sales-db",
  "humanReviewEnabled": false,
  "idempotencyKey": "client-generated-key"
}
```

创建成功后立即返回 `202 Accepted`：

```json
{
  "runId": "run_01",
  "conversationId": "conv_01",
  "status": "queued",
  "eventsUrl": "/api/v1/runs/run_01/events"
}
```

### 10.4 结果与产物

```text
GET /api/v1/artifacts/{artifact_id}
GET /api/v1/result-sets/{result_set_id}?page=1&page_size=100
GET /api/v1/runs/{run_id}/export?format=csv
GET /api/v1/runs/{run_id}/export?format=markdown
```

### 10.5 人工审核

```text
GET  /api/v1/reviews/{review_id}
POST /api/v1/reviews/{review_id}/approve
POST /api/v1/reviews/{review_id}/reject
```

退回请求必须包含修改意见。重复提交返回当前审核状态，不重复恢复工作流。

### 10.6 Agent 与数据源

```text
GET  /api/v1/agents
GET  /api/v1/datasources
POST /api/v1/datasources/{datasource_id}/test
```

第一阶段的 Agent 仅表示配置 Profile，不表示多 Agent 运行时。

## 11. SSE 事件协议

### 11.1 事件信封

```json
{
  "eventId": "evt_01",
  "conversationId": "conv_01",
  "runId": "run_01",
  "seq": 12,
  "type": "stage.completed",
  "stage": "schema_recall",
  "timestamp": "2026-07-01T10:00:02+08:00",
  "data": {}
}
```

`seq` 在单个 Run 内严格递增，用于排序、去重和断线补发。

### 11.2 事件类型

```text
run.started
stage.started
stage.progress
stage.completed
text.delta
artifact.created
review.required
run.completed
run.failed
run.cancelled
heartbeat
```

### 11.3 使用约束

- `text.delta` 只用于最终回答或明确需要流式展示的文本。
- 不保存每个 Token；服务端按时间或字符数聚合后保存最终文本。
- `artifact.created` 只传 Artifact 摘要和 ID。
- `run.completed` 只传终态和 Run URL，前端随后获取完整快照。
- 大结果集、完整 Schema、历史会话和导出文件不得放入 SSE。
- SSE 意外断开不等于任务取消。

### 11.4 前端事件归并

前端必须增加 `AnalysisRunStore` 或等价 Reducer：

```text
SSE Event
→ 校验 runId 与 seq
→ 更新当前阶段和进度
→ 合并 text.delta
→ 收到 artifact.created 后按需加载 Artifact
→ 收到 run.completed 后重新加载 AnalysisRun
```

结果页不得直接从原始 SSE 消息数组推导完整结果。

## 12. 工作流设计

### 12.1 第一阶段流程

```text
START
→ prepare_context
→ classify_intent
→ retrieve_knowledge_and_schema
→ enhance_query
→ choose_execution_path
   ├── simple_query
   └── complex_analysis
→ generate_sql
→ validate_sql
→ request_review_if_needed
→ execute_sql
→ repair_or_continue
→ build_analysis_result
→ END
```

### 12.2 简单查询

简单查询只执行一条 SQL，不强制进入 Planner：

```text
召回
→ SQL 生成
→ 安全检查
→ 执行
→ 总结
```

### 12.3 复杂分析

复杂分析先生成高层目标和成功标准，再进入受控分析循环：

```text
高层规划
→ 决定下一步 Action
→ 安全检查
→ 执行 Action
→ 记录 Observation
→ 继续、澄清或结束
```

允许的 Action：

```text
query_database
inspect_schema
retrieve_knowledge
ask_clarification
finish
```

第一阶段可以先实现固定计划循环，但状态和接口应允许后续替换为上述受控 ReAct。

### 12.4 循环限制

- 分析 Action 最多 5 次。
- SQL 执行最多 3 条。
- 单条 SQL 修复最多 2 次。
- 重复 SQL 连续出现 2 次时终止。
- 所有 SQL 重试必须重新执行安全检查。
- 任务必须配置总时长、模型调用数和 Token 上限。
- 达到上限时产生明确的 `result_mode`，不得静默结束。

## 13. Python 数据分析能力

第一阶段以满足前端为主，不实现任意代码执行。预留结构化分析操作接口：

```text
profile_data
aggregate
trend
compare_groups
detect_anomalies
correlation
top_contributors
distribution
```

推荐使用 DuckDB 或 Polars 对 Parquet 结果进行分析。LLM 只选择操作和参数，后端负责精确计算。

后续若引入模型生成 Python，必须使用独立隔离环境，并限制网络、文件、CPU、内存、执行时间和输出大小。不得在 FastAPI 主进程中直接 `exec` 模型代码。

## 14. 持久化设计

### 14.1 SQLite 保存内容

```text
conversations
messages
analysis_runs
stage_runs
artifacts
queries
review_checkpoints
run_events
result_sets
```

### 14.2 SQLite 配置

```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
```

约束：

- 使用 SQLAlchemy 2 和 Alembic。
- 异步访问使用 `aiosqlite`。
- 数据访问必须经过 Repository，不在业务代码中拼接 SQLite SQL。
- 写事务保持短小，事务期间不调用 LLM 和业务数据库。
- SSE 高频事件批量写入，不逐 Token 写数据库。
- 并发评测使用独立 SQLite 文件或关闭详细事件持久化。

### 14.3 结果集存储

```text
小结果：SQLite JSON
大结果：Parquet 文件
SQLite：列信息、预览、总行数、文件地址、过期时间
```

建议目录：

```text
data/
├── app.db
├── results/
│   └── {run_id}/
│       ├── result_01.parquet
│       └── result_02.parquet
└── exports/
    └── {run_id}/
```

结果文件必须使用服务端生成的 ID 映射，不允许 API 直接接收任意文件路径。

### 14.4 状态生命周期

第一阶段默认值：

| 数据 | 默认保留策略 |
| --- | --- |
| Conversation / Message | 用户删除前保留 |
| AnalysisRun / Artifact 元数据 | 用户删除会话前保留 |
| Checkpoint | 完成后保留 7 天 |
| Run Event | 完成后保留 24 小时 |
| ResultSet 文件 | 30 天，访问时可续期 |
| Export 文件 | 24 小时 |

TTL 必须可配置，并提供定时清理任务。清理文件和数据库记录必须保持一致。

## 15. 会话与上下文

- `conversation_id` 是产品会话标识，不是线程 ID。
- `run_id` 标识一次分析运行。
- LangGraph `thread_id` 可以内部使用 `conversation_id:run_id`，不得暴露为 Java/Python 线程概念。
- 会话上下文采用滚动摘要加最近原始轮次。
- 达到配置轮数后，只归档较旧轮次，保留最近 3 轮原文。
- 摘要、历史消息和当前问题由 Context Builder 统一组装。
- 人工审核恢复依赖 `run_id` 和 Checkpoint，不依赖进程内对象仍然存在。

## 16. SQL 安全

所有 SQL 在执行前依次经过：

1. 解析成功检查。
2. SELECT Only 检查。
3. 多语句检查。
4. 危险函数和系统表检查。
5. Schema 表字段真实性检查。
6. 敏感字段检查。
7. 明细导出与范围检查。
8. LIMIT 策略。
9. 数据源权限检查。
10. 超时和最大结果行数限制。

Planner、ReAct 或人工审核不能绕过这些检查。人工批准表示允许继续流程，不表示关闭安全策略。

## 17. 取消、重试和恢复

### 17.1 取消

- 前端调用 `POST /runs/{run_id}/cancel`。
- 后端设置持久化取消标记。
- 工作流在节点边界检查取消状态。
- 数据库驱动支持时取消正在执行的 SQL。
- 最终状态为 `cancelled`，保留已产生的 Artifact。

### 17.2 重试

- 技术性重试记录在原 Run 的 StageRun attempt 中。
- 用户点击“重新生成”创建新的 Run，并记录 `retry_of_run_id`。
- 幂等键避免网络重试创建重复任务。

### 17.3 断线恢复

- SSE 断开不停止后台任务。
- 前端重连时传 `after_seq` 或 `Last-Event-ID`。
- 若事件已过期，前端直接加载最新 AnalysisRun 快照。
- 服务重启后通过持久化状态恢复可恢复任务；不可恢复任务标记为明确失败。

## 18. 可观察性与评测

每次 Run 至少记录：

- 模型调用次数、Token 和耗时。
- 每个阶段耗时和重试次数。
- Schema、文档和证据召回结果。
- SQL 生成、安全检查、执行和修复记录。
- ResultSet 行数和截断状态。
- 最终 result mode 和错误分类。

评测必须基于 API 和持久化快照，不依赖日志文本解析。第一阶段保留以下核心指标：

- 任务目标通过率。
- 相关表召回率。
- SQL 执行成功率。
- 安全请求保护成功率。
- 多轮上下文正确率。
- 人工审核恢复成功率。
- P50 / P95 总耗时及各阶段耗时。

## 19. 实施阶段

### 阶段 A：契约与静态后端

1. 定义 Pydantic API 模型和 OpenAPI。
2. 建立 SQLite、Alembic 和 Repository。
3. 实现会话、Run、ResultSet、Review API。
4. 用固定数据实现 SSE 和完整 AnalysisRun。
5. 前端移除 `data.ts` 中的分析结果静态数据。

验收标准：前端所有页面都由后端数据填充，即使工作流暂时返回固定分析结果。

### 阶段 B：最短真实工作流

1. 接入真实数据源和 Schema 读取。
2. 接入意图识别、Schema 召回、SQL 生成。
3. 接入确定性 SQL 安全和执行。
4. 接入结构化总结。
5. 打通运行状态、Artifact 和 SSE。

验收标准：单条 SQL 的典型查询能够完整展示过程、结果和错误。

### 阶段 C：复杂分析能力

1. 接入高层规划和受控分析循环。
2. 接入 SQL 修复。
3. 接入人工审核和 Checkpoint 恢复。
4. 接入图表建议和结构化关键发现。
5. 接入 DuckDB / Polars 分析操作。

### 阶段 D：可靠性与评测

1. 取消、重试、幂等和断线补发。
2. TTL 和文件清理。
3. 并发限制、超时和背压。
4. 离线评测迁移和基线对比。
5. 打包、升级和数据迁移验证。

## 20. 第一阶段验收清单

- [x] 欢迎页推荐问题和服务状态来自后端。
- [x] 会话列表支持加载、搜索、重命名和删除。
- [x] 多轮追问复用同一 Conversation。
- [x] 工作区显示真实阶段、耗时和状态。
- [x] 召回表、字段和关系来自 Retrieval Artifact。
- [x] SQL、计划和安全检查来自真实 Artifact。
- [x] 结果页展示真实标题、总结、发现和指标。
- [x] 表格支持分页并显示真实总行数和截断状态。
- [x] 图表只引用真实 ResultSet 字段。
- [x] 人工审核页展示真实计划、SQL 和查询范围。
- [x] 批准和退回能够恢复同一 Run。
- [x] 用户可以取消和重试任务。
- [x] SSE 断开后能够恢复状态。
- [x] 应用重启后能够恢复历史会话和已完成结果。
- [x] 前端不再依赖静态 `sampleSql`、`resultRows` 和 `chartValues`。

## 21. 已确定与待确定事项

### 21.1 已确定

- Python 使用 FastAPI 提供 REST 和 SSE。
- 工作流使用 LangGraph `StateGraph`，人工审核使用 `interrupt/Command`，Checkpoint 使用 SQLite Saver。
- 第一阶段使用 SQLite 保存应用状态。
- 大结果使用 Parquet，本地文件只通过 ID 访问。
- REST 负责完整数据，SSE 负责实时通知。
- 第一阶段采用单 Agent 工作流，不做多 Agent。
- 主流程固定，复杂分析使用有限循环。
- 安全检查由确定性代码执行。
- Skill 暂不实现，只允许保留轻量扩展接口。
- 第一目标是完整满足前端，而不是复制 Java 后端结构。

### 21.2 待确定

- Python 依赖和最低运行版本。
- pgvector 是必需依赖还是可选远程能力。
- 结果集从多少行开始切换到 Parquet。
- 默认循环次数、任务时长和 Token 预算。
- 数据源凭证使用系统 Keychain 还是本地加密存储。
- 是否在阶段 C 开放模型选择结构化 Python 分析操作。

待确定事项不得阻塞阶段 A 的 API 契约和前端数据接入。

## 22. 防止架构跑偏的约束

出现以下情况时必须回到本文档重新评审：

- 前端开始依赖 LangGraph State 或节点内部字段。
- SSE 开始传输完整大结果集或作为唯一数据来源。
- 新增 Agent 但没有单 Agent 失败数据和评测收益。
- 新增 Skill 但无法说明解决哪类重复问题。
- 模型可以绕过 SQL 安全检查。
- 模型生成代码在主进程直接执行。
- 每增加一个工作流节点都需要修改多个前端页面。
- Artifact 字段继续使用无约束的 `dict[str, Any]`。
- SQLite 事务包含 LLM、网络或业务数据库调用。
- 为未来可能出现的规模提前引入分布式基础设施。

后续架构变更应更新本文档的“已确定事项”、API 契约和验收清单。
