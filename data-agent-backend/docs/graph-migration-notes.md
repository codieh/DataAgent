# Graph 编排迁移学习记录

## 1. 目标

这份文档用于记录 `data-agent-backend` 从线性 `SearchLiteOrchestrator` 迁移到 `management` 同款 Graph 编排技术路线的过程。

目标不是只“做一个像图的流程”，而是：

- 真正引入 `spring-ai-alibaba-graph-core`
- 使用 `StateGraph`
- 使用 `NodeAction`
- 后续逐步引入 `Dispatcher + ConditionalEdges`

这样后续在简历中可以明确写成：

- 基于 `spring-ai-alibaba-graph-core` 设计多阶段 Agent 工作流编排
- 将线性 pipeline 升级为 state-driven graph workflow
- 通过条件路由支持提前结束、失败回退与分支控制

---

## 2. 为什么现在开始迁移

当前 `data-agent-backend` 存在一个真实问题：

- `INTENT = CHITCHAT` 时，后续 `EVIDENCE / SCHEMA / SQL` 仍会继续跑

这说明当前的线性 orchestrator 存在天然限制：

- 默认只能 `step1 -> step2 -> step3`
- 不支持根据 state 决定下一步
- 不支持提前结束
- 不支持自然的失败分支

因此，迁移到 Graph 编排不是“为了看起来高级”，而是为了解决实际控制流问题。

---

## 3. management 项目的参考实现

`management` 的编排入口：

- `D:\GitHub\DataAgent\data-agent-management\src\main\java\com\alibaba\cloud\ai\dataagent\config\DataAgentConfiguration.java`

关键特征：

- 使用 `StateGraph`
- 通过 `addNode(...)` 定义节点
- 通过 `addEdge(...)` 定义固定流转
- 通过 `addConditionalEdges(...)` 定义条件分支
- 通过 `Dispatcher` 决定下一步

这条路线非常适合当前项目后续升级。

---

## 4. 当前 backend 的迁移原则

迁移时遵守以下原则：

- 不一次性推翻现有 `SearchLiteStep`
- 优先让 graph 先跑起来，再逐步迁业务逻辑
- 先做最小图骨架，再加条件路由
- 先解决 `INTENT` 的提前结束问题，再迁其他节点

---

## 5. Step G1 完成内容（记录时间：2026-04-01）

本步骤目标：

- 引入 `spring-ai-alibaba-graph-core`
- 建立 backend 的最小 graph 骨架
- 为后续 `G2/G3/G4` 做准备

本步骤已完成：

- 在 `pom.xml` 中加入：
  - `spring-ai-alibaba-graph-core`
- 新增最小 graph 配置类：
  - `SearchLiteGraphConfiguration`
- 新增两个占位节点：
  - `SearchLiteIntentGraphNode`
  - `SearchLiteResultGraphNode`

当前最小图结构：

```text
START -> INTENT_NODE -> RESULT_NODE -> END
```

说明：

- 这是一个“能编译、能作为后续迁移地基”的最小骨架
- 暂时还没有接入现有 controller 与 SSE 主流程
- 暂时也还没有加入 `Dispatcher`

---

## 6. 当前 graph 骨架涉及的类

### 6.1 配置类

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\SearchLiteGraphConfiguration.java`

职责：

- 定义 `StateGraph`
- 定义 state key
- 注册最小节点和边

### 6.2 Intent 节点

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\node\SearchLiteIntentGraphNode.java`

职责：

- 目前是占位节点
- 后续会逐步接入当前 `IntentMinimaxStep` 的业务能力

### 6.3 Result 节点

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\node\SearchLiteResultGraphNode.java`

职责：

- 目前是占位节点
- 后续会逐步接入当前 `Result` 相关能力

---

## 7. G1 之后的后续步骤

### G2：定义 Lite Graph State

把当前 `SearchLiteState` 的核心字段，映射成 Graph 使用的 state key。

### G3：把现有 Step 包装为 Graph Node

优先迁移：

- `Intent`
- `Result`

再逐步迁移：

- `Evidence`
- `Schema`
- `SchemaRecall`
- `Enhance`
- `SqlGenerate`
- `SqlExecute`

### G4：加入第一个 Dispatcher

第一个最重要的条件路由：

- `DATA_ANALYSIS` -> 后续节点
- `CHITCHAT` -> `RESULT / END`

这一步完成后，Graph 编排就会开始体现真实价值。

---

## 8. 学习时要重点理解什么

后续学习 `spring-ai-alibaba-graph-core` 时，建议重点理解这 4 件事：

- `StateGraph` 如何定义节点和边
- `NodeAction` 如何读写 state
- `Dispatcher` 如何决定下一步
- Graph 输出如何与当前 SSE 流式结果结合

---

## 9. 当前判断

当前选择 `management` 同款 Graph 技术路线是合理的，因为它同时满足：

- 与当前仓库上下文一致
- 与 Spring Boot / Spring AI 生态兼容
- 能解决真实控制流问题
- 能明确写进简历

一句话总结：

> `data-agent-backend` 的编排升级，将从线性 step pipeline，逐步迁移到基于 `spring-ai-alibaba-graph-core` 的 state-driven graph workflow。

---

## 10. Step G2 完成内容（记录时间：2026-04-01）

本步骤目标：

- 将当前 `SearchLiteState` 中的关键字段，正式收口为 Graph 可用的 state key
- 避免后续 Node/Dispatcher 开发时到处硬编码字符串
- 为后续 state 映射与 graph 执行打下稳定基础

本步骤已完成：

- 新增 Graph state key 常量类：
  - `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\SearchLiteGraphStateKeys.java`
- 新增 state 映射工具：
  - `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\SearchLiteGraphStateMapper.java`
- 更新 `SearchLiteGraphConfiguration`
  - 让最小 graph 骨架的 `KeyStrategyFactory` 使用完整的 lite state key 集合

### 10.1 当前已映射的 Lite Graph State

当前 Graph state 已覆盖以下字段：

- 基础信息
  - `agentId`
  - `threadId`
  - `query`
- intent
  - `intentClassification`
- evidence / document
  - `evidences`
  - `evidenceText`
  - `evidenceRewriteQuery`
  - `documentText`
- schema
  - `schemaTables`
  - `schemaText`
  - `schemaTableDetails`
  - `recalledTables`
  - `recalledSchemaText`
- enhance
  - `canonicalQuery`
  - `expandedQueries`
- sql / execute
  - `sql`
  - `rows`
- result / error
  - `resultSummary`
  - `error`

### 10.2 为什么要单独抽 `SearchLiteGraphStateKeys`

这一步对后续开发非常重要，因为它带来 3 个好处：

- **统一命名**
  - 后续所有 graph node / dispatcher 都只引用这一份 state key
- **降低迁移成本**
  - 从 `SearchLiteState` 迁到 graph 时，不需要边迁边猜字段名
- **便于学习和文档化**
  - 可以非常清楚地看到当前 graph 实际管理哪些状态

### 10.3 为什么要加 `SearchLiteGraphStateMapper`

这一步的意义是把当前已有的 `SearchLiteState` 和未来 graph 执行衔接起来。

当前它的作用主要是：

- 把 `SearchLiteState` 统一转换成 `Map<String, Object>`
- 为后续：
  - graph 执行入口
  - node 读取状态
  - 新旧编排并行
  做准备

一句话理解：

> `SearchLiteGraphStateMapper` 是线性 pipeline 世界与 graph state 世界之间的第一个桥接层。

### 10.4 G2 完成后的项目状态

到 G2 为止，我们已经具备：

- `spring-ai-alibaba-graph-core` 依赖接入
- 最小 graph 骨架
- 统一的 Graph state key
- 从 `SearchLiteState` 到 graph state 的映射工具

这意味着后续 `G3` 就可以开始把现有 step 逐步包装成真正可执行的 graph node。
