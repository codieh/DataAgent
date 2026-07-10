# Python 后端消息组装说明

本文基于当前 Python 后端代码，说明一条分析请求如何从 SQLite 会话记录进入 LangGraph，如何组装成 OpenAI-compatible 消息，以及 Schema、SQL 结果和历史工具结果如何避免重复进入上下文。

## 1. 四层数据边界

当前实现不再把 LangGraph State 直接整体发送给模型，而是分为四层：

```text
持久化事实层
├── Conversation / Message / Run / Query
├── ResultSetModel 中的结果预览
├── CSV 中的完整查询结果
└── Artifact / RunEvent / 会话摘要

LangGraph 运行状态
├── 当前问题、计划、Schema 和业务知识
├── 当前 SQL、安全校验及执行状态
├── query_results 中的结果引用
├── observations 中的执行摘要
└── messages 中的原生 Tool Call 协议消息

模型输入投影
└── AgentContextBuilder 从运行状态构造有限上下文

前端展示层
└── SSE、Artifact、RunEvent 和结果集接口
```

这四层的区别非常重要：数据被持久化，不代表每轮都要把它完整发送给模型。

## 2. 示例请求

假设会话中已经有一轮对话：

```text
user: 分析一下订单情况
assistant: 已完成订单总体情况分析。
```

用户继续提问：

```text
查询最高消费订单的时间
```

本次请求的标识为：

```text
conversation_id = conv_001
run_id          = run_001
```

## 3. 创建 Run 与保存当前消息

创建分析任务时，当前用户消息先写入 SQLite：

```json
{
  "id": "msg_003",
  "conversation_id": "conv_001",
  "run_id": "run_001",
  "role": "user",
  "content": "查询最高消费订单的时间"
}
```

`GraphAnalysisExecutor` 随后调用会话 `ContextBuilder`。构建历史上下文时会排除当前消息，防止它同时作为历史消息和当前问题出现两次。

## 4. 会话 ContextBuilder

`app/memory/context.py` 负责构建跨 Run 的会话记忆，产物写入初始状态的 `memory_context`：

```json
{
  "summary": "",
  "recentMessages": [
    {"role": "user", "content": "分析一下订单情况"},
    {"role": "assistant", "content": "已完成订单总体情况分析。"}
  ],
  "relatedMessages": [],
  "longTermMemories": [],
  "stats": {
    "recentCount": 2,
    "retrievedCount": 0,
    "estimatedTokens": 22
  }
}
```

它处理的是“会话记忆”，不是 Agent 当前 Run 内部的 Tool Call 历史：

- `summary`：已经归档的旧对话摘要；
- `recentMessages`：仍保留原文的最近对话；
- `relatedMessages`：从旧消息中检索出的相关内容；
- `longTermMemories`：用户偏好、业务规则等长期记忆。

LangGraph 初始状态大致如下：

```python
{
    "run_id": "run_001",
    "conversation_id": "conv_001",
    "query": "查询最高消费订单的时间",
    "contextualized_query": "查询最高消费订单的时间",
    "memory_context": memory_context,
    "agent_iterations": 0,
    "schema_search_count": 0,
    "sql_execution_count": 0,
    "observations": [],
    "query_results": [],
    "python_analyses": []
}
```

## 5. 意图识别消息

意图识别节点把最近原始对话放在前面，最后追加本轮结构化输入：

```json
[
  {"role": "user", "content": "分析一下订单情况"},
  {"role": "assistant", "content": "已完成订单总体情况分析。"},
  {
    "role": "user",
    "content": "{\"currentQuery\":\"查询最高消费订单的时间\",\"memory\":{...}}"
  }
]
```

OpenAI Client 在最前面添加 `INTENT_SYSTEM`。模型返回结构化结果：

```json
{
  "classification": "DATA_ANALYSIS",
  "contextualized_query": "查询消费金额最高的一笔订单及其下单时间",
  "execution_path": "simple"
}
```

后续 Agent 使用 `contextualized_query`，原始 `query` 仍保留在 State 中。

## 6. AgentContextBuilder

`app/workflow/context_builder.py` 是 Agent 模型输入的统一组装入口。`agent_decide` 不再自行序列化整个 State。

第一次决策时生成的 payload 类似：

```json
{
  "query": "查询消费金额最高的一笔订单及其下单时间",
  "memory": {
    "summary": "",
    "relatedMessages": [],
    "longTermMemories": []
  },
  "plan": null,
  "iteration": 1,
  "budgets": {
    "maxIterations": 50,
    "schemaSearchesRemaining": 50,
    "sqlExecutionsRemaining": 50
  },
  "schema": {"tables": []},
  "knowledge": {"documents": [], "evidences": []},
  "activeResult": null,
  "availableResults": [],
  "observations": [],
  "pythonAnalyses": []
}
```

这里已经没有旧实现中的：

```text
queryResults
lastResult
observations[].preview
```

最终 Agent 消息顺序为：

```text
最近原始 user/assistant 对话
→ 当前 payload（作为新的 user 消息）
→ 当前 Run 的 AIMessage / ToolMessage 投影
```

OpenAI Client 再在最前面添加 `AGENT_SYSTEM`。

## 7. 工具如何注册给模型

工具不是写进提示词文本，而是通过 OpenAI 请求的 `tools` 字段注册。当前共有 9 个原生工具：

```text
update_analysis_plan
ask_clarification
search_schema
inspect_tables
retrieve_knowledge
execute_sql
search_history
inspect_query_result
analyze_dataframe
```

`AnalysisToolRegistry.specifications()` 使用 `tool_call_schema` 生成公开参数，因此以下运行时参数不会暴露给模型：

```text
state
tool_call_id
conversation_id
```

例如 `search_schema` 对模型公开的参数只有：

```json
{
  "name": "search_schema",
  "parameters": {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"]
  }
}
```

`state` 与 `tool_call_id` 由 LangGraph 在 ToolNode 执行时注入。

## 8. Schema Tool Call

第一次 Agent 决策通常会返回：

```json
{
  "role": "assistant",
  "tool_calls": [
    {
      "id": "call_schema_1",
      "type": "function",
      "function": {
        "name": "search_schema",
        "arguments": "{\"query\":\"查询消费金额最高的一笔订单及其下单时间\"}"
      }
    }
  ]
}
```

工具执行后，完整 Schema 只写入结构化 State：

```python
{
    "schema": {"tables": [完整表结构]},
    "selected_tables": ["orders"],
    "schema_reasons": {...},
    "schema_search_count": 1
}
```

ToolMessage 不再复制字段详情，只返回引用信息：

```json
{
  "role": "tool",
  "tool_call_id": "call_schema_1",
  "content": "{\"tool\":\"search_schema\",\"ok\":true,\"summary\":\"召回 1 张候选表\",\"tableNames\":[\"orders\"],\"schemaRef\":\"state.schema\"}"
}
```

第二次 `AgentContextBuilder.build()` 会从 `state.schema` 生成一次受 `context_schema_token_budget` 限制的 Schema，模型不会同时收到三份表结构。

## 9. SQL 提交与执行

模型获得 Schema 后调用 `execute_sql`：

```json
{
  "id": "call_sql_1",
  "function": {
    "name": "execute_sql",
    "arguments": "{\"sql\":\"SELECT id, order_date, total_amount FROM orders ORDER BY total_amount DESC LIMIT 1\",\"for_analysis\":false}"
  }
}
```

这个工具只提交候选 SQL，不直接访问数据库：

```text
execute_sql Tool
→ sql_validate
→ 必要时 human_feedback
→ sql_execute
```

`sql_execute` 执行成功后：

1. 完整结果写入 CSV；
2. SQLite `ResultSetModel` 保存列、预览、总行数和 CSV 路径；
3. `query_results` 只记录当前 Run 的结果引用；
4. observation 只记录摘要、行数和 `datasetId`。

```json
{
  "query_results": [
    {
      "datasetId": "result_001",
      "sql": "SELECT ... LIMIT 1",
      "columns": [
        {"name": "id", "dataType": "integer"},
        {"name": "order_date", "dataType": "datetime"},
        {"name": "total_amount", "dataType": "number"}
      ],
      "rowCount": 1,
      "dataset": {
        "id": "result_001",
        "rowCount": 1,
        "filePath": "data/datasets/result_001.csv"
      }
    }
  ],
  "observations": [
    {
      "tool": "execute_safe_sql",
      "ok": true,
      "summary": "查询成功，返回 1 行",
      "rowCount": 1,
      "datasetId": "result_001"
    }
  ]
}
```

为了兼容当前结果展示，State 仍有 `columns` 和 `rows`，但 `AgentContextBuilder` 不读取这份 rows，因此不会与模型输入中的结果重复。

## 10. 当前结果如何进入下一轮

第三次 Agent 决策前，`AgentContextBuilder` 读取最新 `datasetId`，通过 `ResultHistoryService.inspect()` 从 CSV 或 SQLite 获取有限预览：

```json
{
  "activeResult": {
    "datasetId": "result_001",
    "columns": ["省略"],
    "rows": [
      {
        "id": 38291,
        "order_date": "2025-11-11T20:18:32",
        "total_amount": 12480.0
      }
    ],
    "rowCount": 1,
    "returnedRows": 1,
    "hasMore": false,
    "truncated": false,
    "sql": "SELECT ... LIMIT 1"
  }
}
```

这份数据只出现一次。没有对应的 `queryResults[].rows`、`lastResult.rows` 或 `observations[].preview`。

模型确认结果足够后返回普通 Assistant Message，不再产生 Tool Call，LangGraph 转入 `result` 节点。

## 11. 历史结果目录与历史搜索

`AgentContextBuilder` 还会读取当前会话最近 5 个结果的元数据，排除当前 `activeResult`：

```json
{
  "availableResults": [
    {
      "datasetId": "result_old_01",
      "question": "统计各省销售额",
      "sql": "SELECT province, SUM(...) ...",
      "columns": ["province", "sales_amount"],
      "rowCount": 31,
      "createdAt": "2026-07-06T12:00:00+00:00"
    }
  ]
}
```

目录不携带结果行。用户说“继续分析刚才的数据”时：

```text
availableResults 能唯一确认结果
→ inspect_query_result(dataset_id)

目录无法确认或结果更早
→ search_history(query)
→ 得到 datasetId
→ inspect_query_result(dataset_id)
```

`search_history` 使用 SQLite FTS5 搜索问题、SQL 和列名；若没有 FTS 命中，再使用结构化查询回退。

两个工具的 `conversation_id` 都来自 InjectedState，模型无法指定其他会话。`inspect_query_result` 还会通过 Run 与 ResultSet 的关联再次校验归属。

## 12. Tool Message 投影

`state.messages` 使用 LangGraph `add_messages` reducer 保存当前 Run 的原生消息链：

```text
AIMessage(tool_call)
→ ToolMessage(tool_result)
→ AIMessage(tool_call)
→ ToolMessage(tool_result)
```

发送模型前，`AgentContextBuilder` 创建副本并执行投影：

- Schema ToolMessage 只保留表名和 `schemaRef`；
- 普通短 ToolMessage 原样保留；
- 投影不修改 checkpoint 中的原始消息；
- Assistant Tool Call 和 ToolMessage 保持配对。

`inspect_query_result` 返回的数据行只存在于它自己的 ToolMessage 中，不会再写入 observation preview。

## 13. Result 节点

结果整理节点不发送 Agent 的完整 Tool Calling 历史。它根据最新 `datasetId` 再读取一次最多 50 行预览，并构造独立 payload：

```json
{
  "query": "查询消费金额最高的一笔订单及其下单时间",
  "sql": "SELECT ... LIMIT 1",
  "result": {
    "datasetId": "result_001",
    "columns": ["省略"],
    "rows": ["省略"],
    "rowCount": 1
  },
  "python_analyses": []
}
```

模型返回结构化 `AnalysisOutput`。后端校验图表字段后，将分析结果保存为 Artifact，并把摘要作为 Assistant Message 写入 SQLite。

## 14. OpenAI 请求标准化

`app/infrastructure/llm/openai.py` 将字典消息、`AIMessage` 和 `ToolMessage` 统一转换为 OpenAI 格式：

```json
{
  "model": "kimi-for-coding",
  "temperature": 0.6,
  "messages": [
    {"role": "system", "content": "AGENT_SYSTEM"},
    {"role": "user", "content": "历史用户消息"},
    {"role": "assistant", "content": "历史助手消息"},
    {"role": "user", "content": "当前 Agent payload"},
    {"role": "assistant", "tool_calls": ["省略"]},
    {"role": "tool", "tool_call_id": "call_schema_1", "content": "工具结果"}
  ],
  "tools": ["9 个原生工具定义"],
  "tool_choice": "auto",
  "parallel_tool_calls": false
}
```

项目不主动设置输出 `max_tokens`。输入发送前仍受 `max_context_size=200000` 控制；当消息接近阈值时，LLM Client 的上下文压缩逻辑会保留近期消息并压缩更早内容。

## 15. 完整数据流

```text
用户提交问题
→ SQLite 保存当前 Message 和 Run
→ ContextBuilder 构建会话摘要、最近消息和长期记忆
→ LangGraph 初始化 AnalysisState
→ Intent 节点识别并改写当前问题
→ AgentContextBuilder 构造模型输入
→ Agent 通过原生 Tool Calling 选择动作
→ search_schema 将完整 Schema 写入 State，只返回精简 ToolMessage
→ execute_sql 提交候选 SQL
→ SQL 安全校验 / 人工审核 / SQL 执行
→ ResultSetModel + CSV 持久化结果
→ AgentContextBuilder 通过 datasetId 读取一次 activeResult
→ Agent 决定继续调用工具或结束
→ Result 节点读取结果并生成最终分析
→ Artifact、RunEvent 和 Assistant Message 持久化
```

## 16. 相关代码

| 职责 | 文件 |
| --- | --- |
| 会话记忆组装 | `data-agent-python-backend/app/memory/context.py` |
| Run 初始化与产物持久化 | `data-agent-python-backend/app/application/executor.py` |
| Agent 模型输入投影 | `data-agent-python-backend/app/workflow/context_builder.py` |
| Agent 决策与结果整理 | `data-agent-python-backend/app/workflow/nodes/analysis.py` |
| LangGraph State | `data-agent-python-backend/app/workflow/state.py` |
| 原生工具与 ToolMessage | `data-agent-python-backend/app/workflow/tools.py` |
| 历史结果搜索与读取 | `data-agent-python-backend/app/analysis/history.py` |
| 结果集 CSV 存储 | `data-agent-python-backend/app/analysis/datasets.py` |
| OpenAI 消息标准化与压缩 | `data-agent-python-backend/app/infrastructure/llm/openai.py` |
| 系统提示词 | `data-agent-python-backend/app/workflow/prompts.py` |
