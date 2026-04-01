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

---

## 11. Step G3 完成内容（记录时间：2026-04-01）

本步骤目标：

- 不重写现有业务逻辑
- 先把当前已经可用的 `IntentMinimaxStep` / `ResultMinimaxStep` 包装进 graph node
- 建立一套“step 世界”和“graph 世界”之间的桥接模式

本步骤已完成：

- `SearchLiteIntentGraphNode`
  - 不再是占位节点
  - 已经开始真正复用 `IntentMinimaxStep`
- `SearchLiteResultGraphNode`
  - 不再是占位节点
  - 已经开始真正复用 `ResultMinimaxStep`
- 新增桥接基类：
  - `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\node\SearchLiteStepGraphNodeSupport.java`
- `SearchLiteGraphStateMapper`
  - 新增 `toSearchLiteState(OverAllState)`，支持从 graph state 反向还原 `SearchLiteState`

### 11.1 G3 采用的核心桥接模式

这一步最重要的不是“把两个节点接进去了”，而是形成了后续节点迁移都能复用的桥接模式：

1. Graph node 从 `OverAllState` 读取 state
2. 通过 `SearchLiteGraphStateMapper.toSearchLiteState(...)` 还原为 `SearchLiteState`
3. 创建 `SearchLiteContext`
4. 直接调用现有 step：
   - `step.run(context, state)`
5. 取 `updatedState().block()`
6. 再通过 `SearchLiteGraphStateMapper.fromSearchLiteState(...)` 回写成 graph state map

一句话理解：

> G3 的关键成果，是证明了我们可以**先复用现有 step 逻辑，再逐步完成 graph 化**，而不是必须推倒重写。

### 11.2 为什么现在先忽略 messages，而只取 updatedState

当前 graph node 里，真正被消费的是：

- `SearchLiteStepResult.updatedState()`

而不是：

- `SearchLiteStepResult.messages()`

这是一个刻意的阶段性选择。

原因是：

- 现在 G3 的目标是先完成“业务执行逻辑迁移”
- SSE / Graph streaming 的衔接放到后续 `G6`

也就是说：

- **G3 先迁执行**
- **G6 再迁流式输出**

这样更稳，也更容易定位问题。

### 11.3 新增的桥接基类有什么意义

新增的 `SearchLiteStepGraphNodeSupport` 有两个作用：

- 统一 graph -> step -> graph 的执行模板
- 避免每个 graph node 都重复写：
  - state 还原
  - context 创建
  - `updatedState().block()`
  - state 回写

这一步对后续非常重要，因为后面迁：

- `Evidence`
- `Schema`
- `SchemaRecall`
- `Enhance`
- `SqlGenerate`
- `SqlExecute`

时，都可以沿用这套模板。

### 11.4 G3 完成后的当前状态

到 G3 为止，当前 Graph 迁移已经具备：

- Graph 依赖接入
- 最小 Graph 骨架
- 统一 state key
- state 双向映射
- `Intent` / `Result` graph node 开始复用现有 step 逻辑

这说明 Graph 迁移已经从“骨架搭建阶段”正式进入“业务逻辑迁移阶段”。

### 11.5 当前仍未完成的部分

G3 之后，仍然有几个关键缺口：

- 还没有 `Dispatcher`
  - 所以 `INTENT != DATA_ANALYSIS` 仍然不能提前结束
- 还没有接入当前 controller / orchestrator 主执行入口
- 还没有把 Graph 执行过程输出为当前 SSE 流

因此，G3 的定位应该理解为：

> Graph 节点已经开始承接真实业务逻辑，但 Graph 还没有正式成为主编排入口。

### 11.6 当前验证情况

本步骤已补充 graph node 单测：

- `SearchLiteIntentGraphNodeTest`
- `SearchLiteResultGraphNodeTest`

但 Maven 侧验证当前仍受到本地依赖写入权限影响：

- `D:\GitHub\DataAgent\.m2repo`

因此，这一阶段的测试结论应理解为：

- 代码结构已完成
- 验证仍受本地 Maven 环境限制

---

## 12. Step G4 完成内容（记录时间：2026-04-01）

本步骤目标：

- 为 graph 加入第一个真正的条件路由
- 让 `INTENT` 节点不再固定流向下一个节点
- 开始对齐 `management` 中的 `Dispatcher + ConditionalEdges` 设计

本步骤已完成：

- 新增 `SearchLiteIntentDispatcher`
  - `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\dispatcher\SearchLiteIntentDispatcher.java`
- 更新 `SearchLiteGraphConfiguration`
  - 从固定边：
    - `INTENT -> RESULT`
  - 改为条件边：
    - `INTENT --(DATA_ANALYSIS)--> RESULT`
    - `INTENT --(CHITCHAT/empty)--> END`
- 新增 dispatcher 单测：
  - `D:\GitHub\DataAgent\data-agent-backend\src\test\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\dispatcher\SearchLiteIntentDispatcherTest.java`

### 12.1 G4 为什么很关键

G1-G3 主要解决的是：

- graph 依赖接入
- state 管理
- step 复用

而 G4 开始真正解决当前项目的**控制流问题**：

- 不再默认每个节点都只能走到“下一个固定节点”
- 节点执行完成后，可以根据 state 决定下一步

这一步正是从：

- 线性 pipeline 思维

向：

- state-driven graph workflow 思维

迈出的第一步。

### 12.2 当前条件路由的具体行为

当前 `SearchLiteIntentDispatcher` 的规则非常简单，但已经足够体现 graph 的价值：

- 当 `intentClassification = DATA_ANALYSIS`
  - 路由到 `RESULT_NODE`
- 当 `intentClassification = CHITCHAT`
  - 直接路由到 `END`
- 当分类缺失或为空
  - 也直接路由到 `END`

这和当前最小 graph 骨架是配套的。

因为目前 graph 中只真正迁入了两个业务节点：

- `INTENT`
- `RESULT`

所以这里先让：

- `DATA_ANALYSIS -> RESULT`
- `CHITCHAT -> END`

是一个合理的阶段性选择。

### 12.3 和 management 的对应关系

这一步是直接借鉴 `management` 的写法：

- `StateGraph.addConditionalEdges(...)`
- `EdgeAction`
- `edge_async(dispatcher)`

也就是说，现在 backend 的 graph 编排已经不只是“长得像图”，而是已经开始采用与 `management` 一致的核心控制流机制。

### 12.4 当前图结构（G4 后）

当前最小 graph 现在可以理解为：

```text
START -> INTENT
INTENT -> RESULT (when DATA_ANALYSIS)
INTENT -> END    (when CHITCHAT / empty)
RESULT -> END
```

### 12.5 这一步仍然是阶段性实现

需要特别注意：

- 这一步还没有把 `EVIDENCE / SCHEMA / SQL` 节点迁入 graph
- 所以 `DATA_ANALYSIS` 目前仍然先去 `RESULT`
- 这只是为了先证明条件路由机制已经成立

真正的下一阶段目标会是：

- 把 `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`
- `SQL_GENERATE`
- `SQL_EXECUTE`

逐步迁入 graph，再把 `DATA_ANALYSIS` 的路由改到真正的后续分析链路。

### 12.6 G4 对学习这套框架最有帮助的点

如果从“理解 graph 框架”角度看，G4 最值得记住的是这句话：

> Node 负责“产出状态”，Dispatcher 负责“决定下一步”。

这就是 `management` 里最核心的编排思想之一。
