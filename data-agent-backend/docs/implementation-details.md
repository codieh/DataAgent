# 🧩 `data-agent-backend` 功能实现细节

这份文档专门解释：

- 当前项目每个主要功能是怎么实现的
- 关键类之间如何协作
- 哪些地方是简化实现
- 哪些地方已经开始向 `data-agent-management` 靠拢

适合在下面几种场景里使用：

- 一段时间没看项目，想快速找回感觉
- 准备写简历 / 面试讲解
- 后续继续做 recall / RAG / 编排优化

---

## 1. 请求是怎么进来的

主入口：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\controller\SearchLiteController.java`

这个接口负责：

- 接收 `agentId / threadId / query`
- 创建 `SearchLiteRequest`
- 调用 `SearchLiteOrchestrator`
- 把每一步返回的 `SearchLiteMessage` 转成 SSE

所以从代码链路上说，真正的执行起点是：

> `orchestrator.stream(new SearchLiteRequest(...))`

---

## 2. 编排器是怎么驱动整条流水线的

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\SearchLiteOrchestrator.java`

它的核心职责：

- 拿到 Spring 注入的 `List<SearchLiteStep>`
- 按 `@Order` 顺序执行
- 将每个 step 的消息流拼起来
- 将每个 step 对 `SearchLiteState` 的修改串起来
- 统一做错误兜底

### 为什么它“知道下一个 step 是谁”

不是因为 Java 自动识别实现类，而是因为：

- 所有 step 都实现了 `SearchLiteStep`
- Spring 会把这些 bean 收集成 `List<SearchLiteStep>`
- 再按 `@Order` 排序

所以本质是：

> **显式顺序编排**

不是 Graph，不是自动推理。

---

## 3. State 在项目里扮演什么角色

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\api\lite\SearchLiteState.java`

它是整条流水线的共享上下文。

### 目前主要保存的内容

- 请求基础信息
  - `agentId`
  - `threadId`
  - `query`
- 意图识别结果
  - `intentClassification`
- 证据召回结果
  - `evidences`
  - `evidenceText`
  - `evidenceRewriteQuery`
- schema 结果
  - `schemaTables`
  - `schemaText`
  - `schemaTableDetails`
  - `recalledTables`
  - `recalledSchemaText`
- query 增强结果
  - `canonicalQuery`
  - `expandedQueries`
- SQL 与执行结果
  - `sql`
  - `rows`
  - `resultSummary`
  - `error`

### 为什么它重要

因为每个 step 都不是独立的小黑盒，而是：

- 读取上游结果
- 写入自己的产物
- 供下游继续使用

---

## 4. 各个 Step 是怎么实现的

---

### 4.1 `INTENT`

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\step\impl\IntentMinimaxStep.java`

实现方式：

- 构造 system prompt + user prompt
- 调用 `AnthropicClient.streamMessage(...)`
- 将模型 delta 直接转成 SSE 消息
- 同时把所有 delta 拼成完整字符串
- 最终解析 JSON：
  - `classification`
  - `reason`
- 写回 `SearchLiteState.intentClassification`

这一步的关键点：

- **是真流式**
- 同一条流被消费两次，所以用了 `cache()`

---

### 4.2 `EVIDENCE`

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\step\impl\EvidenceFileStep.java`

当前实现已经分成两层：

#### 第一层：evidence query rewrite

相关类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\EvidenceQueryRewriteService.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\MinimaxEvidenceQueryRewriteService.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\NoopEvidenceQueryRewriteService.java`

作用：

- 把原始用户问题改写成更适合 evidence 检索的 standalone query
- 当前支持：
  - `none`
  - `minimax`

#### 第二层：RecallService 做 evidence 召回

相关类：

- `RecallService`
- `EvidenceIndexBuilder`
- `EvidenceRecallMetadataResolver`

流程：

- 从本地 evidence 索引读取文档
- 如果没有索引，则从 `evidence.json` 构建
- 根据 query 推断 topic/tags
- 先做 metadata 过滤召回
- 如果没命中，再 fallback 全量召回
- 选出 topK evidence
- 生成 `evidenceText`
- 写回 state

这里已经开始参考 management：

- evidence recall 前先 rewrite
- recall 时不是无差别全量检索

---

### 4.3 `SCHEMA`

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\step\impl\SchemaMysqlIntrospectStep.java`

作用：

- 从 MySQL 的 schema 中抽取：
  - 表
  - 列
  - 注释
  - 外键

当前实现有两条路径：

- 优先从本地持久化 schema 索引读取
- 如果没有，再查数据库并构建索引

这说明它已经不是“纯运行时查库”，而是：

> **索引优先 + 缺失时 fallback 实时构建**

---

### 4.4 `SCHEMA_RECALL`

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\step\impl\SchemaRecallStep.java`

底层依赖：

- `RecallService.recallSchema(...)`

当前实现方式：

- query + evidenceText 合并成检索 query
- 先召回 `SCHEMA_TABLE`
- 再基于召回表名过滤 `SCHEMA_COLUMN`
- 生成 `recalledSchemaText`
- 写回 state

这是当前项目里非常关键的一步，因为它让 SQL 生成不再只依赖全量 schema。

---

### 4.5 `ENHANCE`

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\step\impl\EnhanceMinimaxStep.java`

作用：

- 生成：
  - `canonicalQuery`
  - `expandedQueries`

实现方式：

- 调用 LLM 输出 JSON
- 解析为结构化结果
- 对结果做标准化：
  - `canonicalQuery` 兜底原 query
  - `expandedQueries` 去重并保证 canonical 在第一位

这一步的目的不是“改写得更好看”，而是：

> 让后面的 SQL 生成更稳定

---

### 4.6 `SQL_GENERATE`

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\step\impl\SqlGenerateMinimaxStep.java`

输入：

- `effectiveQuery`
- `evidenceText`
- `recalledSchemaText`

实现方式：

- 使用 prompt 明确约束：
  - 只生成 SQL
  - 保留 limit
  - 不输出多余解释
- 流式输出 SQL delta
- 最终写入 `state.sql`

这里使用的是：

- `SearchLiteState.getEffectiveQuery()`

也就是说：

- 优先用 `canonicalQuery`
- 没有就回退原 query

---

### 4.7 `SQL_EXECUTE`

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\step\impl\SqlExecuteJdbcStep.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\sql\SqlGuards.java`

它做两件事：

#### 先做 guardrails

- 只允许 `SELECT`
- 禁止多语句
- 自动补 limit
- 限制危险模式

#### 再做 JDBC 查询

- 使用 `JdbcTemplate`
- 在 `boundedElastic` 执行
- 超时控制
- 返回 rows / columns

执行失败时：

- 不会直接把整条流炸掉
- 会转成 SSE error / state.error

---

### 4.8 `RESULT`

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\step\impl\ResultMinimaxStep.java`

作用：

- 对结果集做自然语言总结

实现方式：

- 如果执行阶段已经报错，则直接输出失败总结
- 否则基于：
  - SQL
  - rows
  - rowCount
  生成总结

---

## 5. Recall 基础设施是怎么实现的

这是当前项目最值得重点讲的一层。

---

### 5.1 统一文档模型

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\RecallDocument.java`
- `RecallHit.java`
- `RecallOptions.java`

作用：

- 把 schema、evidence、后续 document 都统一成一种可召回对象

这样后续新增类型时，不需要重写整套 recall 逻辑。

---

### 5.2 索引构建

核心类：

- `EvidenceIndexBuilder`
- `SchemaIndexBuilder`

#### EvidenceIndexBuilder

会把 `EvidenceItem` 转成 `RecallDocument`，并补：

- `topic`
- `tags`
- `source`
- `type`

#### SchemaIndexBuilder

会把 schema 拆成：

- `SCHEMA_TABLE`
- `SCHEMA_COLUMN`

这已经非常接近 management 的文档化思路了。

---

### 5.3 召回引擎

#### `KeywordRecallEngine`

实现方式：

- 对 query 和文档做 token 化
- title/content 命中打分
- metadata 过滤
- TopK 返回

#### `VectorRecallEngine`

实现方式：

- 对 query 做 embedding
- 读取文档 embedding
- 做余弦相似度

#### `HybridRecallEngine`

实现方式：

- 同时计算 keyword recall 与 vector recall
- 融合：
  - `keywordScore`
  - `vectorScore`
  - `fusedScore`

当前还是起步版，但已经具备后续继续调权重的空间。

---

### 5.4 本地索引存储

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\store\FileRecallDocumentStore.java`

当前做法：

- 索引落地到本地 JSON 文件
- 启动后可读取
- 可手动重建

当前文件包括：

- `evidence-index.json`
- `schema-index.json`

这是我们当前对 management “init + recall” 思路的轻量实现。

---

### 5.5 RecallService

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\RecallService.java`

它是 recall 的统一协调者。

Evidence 侧：

- 读索引
- 缺失时重建
- 补 embedding
- metadata 过滤
- recall
- fallback

Schema 侧：

- 读 schema 索引
- 缺失时构建
- 先召回表
- 再召回列

也就是说：

> `RecallService` 已经是当前项目 recall 子系统的核心。

---

## 6. 向量化是怎么接进来的

核心类：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\embedding\LocalEmbeddingClient.java`

当前方式：

- 调本地 embedding 服务：
  - `http://localhost:11434/v1/embeddings`
- model:
  - `bge-m3`

实现细节：

- 使用 JDK `HttpClient`
- 返回 embedding 向量
- 写入 recall 文档 metadata

配合：

- `RecallEmbeddingService`

作用：

- 确保索引文档有 embedding
- 没有就补齐

---

## 7. 索引初始化接口怎么工作

控制器：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\controller\RecallIndexController.java`

支持：

- `POST /api/index/init/evidence`
- `POST /api/index/init/schema`
- `POST /api/index/init/all`
- `GET /api/index/status`

它的实现要点：

- 初始化是阻塞工作
- 所以运行在 `boundedElastic`
- 避免阻塞 WebFlux 事件线程

这是之前修过的一个关键点。

---

## 8. 当前项目和 management 已经靠近到什么程度

已经靠近的部分：

- evidence/schema 文档化
- init + recall 思路
- metadata 过滤思路
- evidence recall 前 query rewrite
- table -> column 两段式 schema recall
- keyword / vector / hybrid recall

还没完全达到的部分：

- agentId 级知识范围控制
- datasourceId 级 schema 边界
- 完整 Graph 编排
- 文档型 RAG 正式接入
- 更完整的评测治理

---

## 9. 当前项目最值得继续优化的点

### 9.1 完善 recall

重点：

- 继续优化 evidence / schema / hybrid
- 做 recall 效果诊断与量化

### 9.2 接入 document RAG

方向：

- 新增 `DOCUMENT` 类型
- 本地文档读取 + chunk
- 建立文档索引
- 接入主链路

### 9.3 落地评测系统

方向：

- dataset
- evaluator
- metrics
- report

---

## 10. 一句话总结

当前这个项目的实现，本质上已经不是“简单调用一次模型”，而是：

> **用一个可观测的多阶段流水线，把 query、检索、schema、SQL 与结果总结组织成了一个精简版数据分析 Agent。**

它现在最强的部分在于：

- 主链路完整
- recall 基础设施开始成型
- 后续还能自然接 document RAG、评测系统和更强编排
