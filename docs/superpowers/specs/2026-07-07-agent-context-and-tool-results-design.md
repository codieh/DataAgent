# Agent 上下文与工具结果管理设计

## 目标

在不丢失历史分析能力的前提下，消除 Schema、SQL 结果和 Tool Message 在模型输入中的重复，避免上下文随查询次数和结果规模线性增长。

设计同时满足以下要求：

- 当前分析过程连续，模型无需为了刚产生的结果再次调用工具。
- 历史查询可搜索、可复用，并保持结果生成时的数据快照。
- 完整记录可供前端展示和问题审计，但不等于每次都发送给模型。
- Tool Call 与 Tool Message 始终保持协议配对。
- 接近 200K 上下文限制时，先裁剪可恢复的工具输出，再压缩旧对话。

## 总体边界

```text
持久化事实层
├── Conversation / Run / Query
├── ResultSetModel + CSV
├── 完整 Tool Call 轨迹
└── 会话摘要

运行状态层（LangGraph State）
├── 当前任务与计划
├── 当前 Schema 引用
├── 当前结果 datasetId
├── 工具执行状态
└── 路由与错误状态

AgentContextBuilder（模型输入投影）
├── 当前会话摘要
├── 最近原始对话
├── 当前 Schema
├── 当前结果预览
├── 历史结果目录
└── 精简 Tool Messages

Agent 工具
├── search_history
└── inspect_query_result

展示与审计层
├── RunEvent
├── Artifact
├── 完整 observations
└── 前端 SSE / 历史详情
```

四层职责不可混用：事实层保存完整数据，运行状态层驱动图执行，`AgentContextBuilder` 决定模型能看到什么，展示层服务前端和排错。

## 持久化事实层

### 查询与结果

`Query` 记录用户问题、SQL、执行状态、所属 run 和结果集引用。`ResultSetModel` 保存列定义、预览、总行数和 CSV 路径，CSV 保存完整结果。

结果集是历史数据的事实源。后续分析通过 `datasetId` 读取原结果，不重新执行 SQL，避免数据库变化造成前后结果不一致。

### 工具轨迹

完整 Tool Call 与 Tool Result 持久化，用于：

- 前端展示完整分析过程；
- 调试和审计；
- 恢复未完成的运行；
- 评测 Agent 的工具选择。

持久化内容不会原样自动进入模型上下文。

### 会话摘要

会话摘要只保存用户目标、已确认结论、关键约束、重要结果引用和未完成事项。精确表结构和数据行不写入摘要，而是保存对应引用。

## 运行状态层

LangGraph state 只保存当前 run 的执行状态和事实引用，不承担历史检索职责。

当前结果使用以下结构：

```json
{
  "datasetId": "result_123",
  "sql": "SELECT ...",
  "rowCount": 31,
  "columns": ["province", "sales_amount"]
}
```

不再同时维护 `state.rows`、`query_results[].rows`、`observations[].preview` 和 `lastResult` 四份行数据。需要预览时，由 `AgentContextBuilder` 或结果整理节点根据 `datasetId` 从结果存储读取一次。

`observations` 可以保留在展示与审计数据中，但运行状态里的 observation 只包含工具名、状态、摘要、错误和资源引用。

## AgentContextBuilder

`AgentContextBuilder` 是所有 Agent LLM 请求的唯一入口。节点不得自行把整个 state 序列化后发送给模型。

### 热上下文

每次决策默认包含：

- 当前用户问题；
- 会话摘要；
- 最近原始对话；
- 当前计划和剩余执行预算；
- 当前 Schema 的预算化视图；
- 当前 run 最新结果的有限预览；
- 当前工具调用链。

当前结果只出现一次。若预览已经位于最近 Tool Message 中，payload 不再重复注入。

### 历史结果目录

默认注入当前会话最近少量结果的元数据，不注入行数据：

```json
{
  "datasetId": "result_123",
  "question": "统计各省销售额",
  "columns": ["province", "sales_amount"],
  "rowCount": 31,
  "createdAt": "2026-07-07T10:00:00Z"
}
```

目录用于处理“继续分析刚才的数据”。更早或不明确的历史结果通过 `search_history` 查找。

### Tool Message 投影

持久化轨迹保持完整；发送给模型前生成精简副本：

- 最近且当前步骤需要的 Tool Result 保留正文；
- Schema 工具只保留表名、召回原因和 `schemaRef`；
- SQL 提交工具只保留校验状态；
- 旧查询结果只保留 `datasetId`、行数和已压缩标记；
- 错误结果保留错误类型、原因和是否可重试；
- Assistant Tool Call 与对应 Tool Message 一起保留或一起移出上下文。

模型输入投影不得修改原始 checkpoint 和审计轨迹。

## Agent 工具

### search_history

用途是定位历史分析产物，相当于受控的会话级 grep。

输入：

```text
query: string
scope: query_results | analyses | all
limit: 1..10
```

搜索字段包括用户问题、SQL、列名、分析摘要和工具摘要。实现使用 SQLite FTS5，并强制限定当前 `conversation_id`。

输出只包含匹配摘要和资源引用，不包含完整结果行。

### inspect_query_result

用途是读取确定结果集的具体数据。

输入：

```text
dataset_id: string
offset: non-negative integer
limit: 1..50
```

执行前必须验证 `datasetId` 通过 Query/Run 归属于当前 `conversation_id`。优先读取 CSV；CSV 因 TTL 被清理后，返回 SQLite 中保留的预览，并标记 `truncated=true`。

工具结果是当前步骤读取数据的唯一模型输入位置，不再复制到 payload 和 observations。

## 上下文治理顺序

每次请求模型前按以下顺序控制上下文：

1. 对 Schema、知识和结果预览应用各自预算。
2. 将较旧的大型 Tool Result 替换为资源引用。
3. 仅保留最近完整工具调用链和最近原始对话。
4. 若仍接近 200K 限制，更新会话摘要并移除已被摘要覆盖的旧消息。
5. 在完整 user turn 或完整 Tool Call/Tool Message 边界裁剪，禁止产生孤立消息。

Token 优先使用模型 API 返回的 usage；本轮尚未请求模型的新增内容使用本地估算。

## 数据流

### 当前查询

```text
用户问题
→ AgentContextBuilder 组装上下文
→ Agent 召回 Schema
→ 完整 Schema 写入运行事实，Tool Message 返回精简表名
→ Agent 提交 SQL
→ 安全检查与执行
→ ResultSetModel + CSV 持久化
→ state 只记录 datasetId 和元数据
→ AgentContextBuilder 读取一次当前结果预览
→ Agent 继续分析或结束
```

### 历史结果复用

```text
用户：根据之前的地区销售结果继续分析
→ 最近结果目录能唯一命中：直接 inspect_query_result
→ 无法唯一命中：search_history("地区销售")
→ 获得 datasetId
→ inspect_query_result(datasetId)
→ 基于原始结果继续分析
```

## 错误处理与安全

- 历史搜索和结果读取必须绑定当前 `conversation_id`。
- 不存在或越权的 `datasetId` 返回统一的不可读取结果，不泄露资源是否属于其他会话。
- CSV 丢失时降级到 SQLite 预览；若两者都不存在，提示结果已失效，而不是自动重跑 SQL。
- FTS 搜索失败时降级为当前会话最近结果的结构化匹配。
- Tool Message 裁剪失败不得影响原始记录，只回退到更保守的字符截断。
- 压缩失败时保留现有上下文，并在下一次调用前给出明确错误，不静默丢弃历史。

## 测试标准

### 去重

- 一次模型请求中完整 Schema 最多出现一次。
- 同一批 SQL 行数据最多出现一次。
- observation 和旧 Tool Message 不包含完整 Schema 或结果预览。

### 连续性

- 当前查询结束前，Agent 能直接使用刚产生的结果。
- 第二轮能通过最近结果目录继续分析第一轮结果。
- 多个相似历史结果存在时，Agent 能先搜索再读取正确结果。

### 安全与恢复

- 不能读取其他会话的结果集。
- CSV 过期后能读取 SQLite 预览并识别截断状态。
- Tool Call 与 Tool Message 在裁剪和压缩后仍严格配对。
- 会话摘要不覆盖最近原始消息，也不丢失重要 datasetId 引用。

### 性能

- Prompt 大小不随历史结果行数线性增长。
- 历史结果目录受固定条数和 Token 预算约束。
- search_history 和 inspect_query_result 均有严格结果数量限制。

## 实施范围

本次实现包含：

- 建立统一 `AgentContextBuilder`；
- 清理 Schema、SQL 结果和 observations 的重复模型输入；
- 增加历史结果 FTS 索引与查询服务；
- 注册 `search_history` 和 `inspect_query_result` 原生工具；
- 增加 Tool Message 投影与上下文治理；
- 调整结果整理节点按 `datasetId` 读取结果；
- 增加上述回归测试。

不在本次范围内：跨会话共享结果、自动重新执行过期 SQL、向量化历史结果搜索和多用户结果共享。
