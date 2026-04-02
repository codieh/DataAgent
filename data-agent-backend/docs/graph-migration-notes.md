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

---

## 13. Step G5 完成内容（记录时间：2026-04-01）

本步骤目标：

- 让 Graph 不再只是“代码里存在”，而是开始真正接入运行链路
- 解决当前用户最直观的问题：
  - `CHITCHAT` 仍然会继续进入 `EVIDENCE / SCHEMA / SQL`
- 保持迁移过程可控，不一次性替换整条旧 pipeline

本步骤已完成：

- 新增 Graph 运行服务：
  - `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\SearchLiteGraphService.java`
- 新增 Graph 执行结果对象：
  - `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\SearchLiteGraphExecutionResult.java`
- 新增 `SearchLiteContinueGraphNode`
  - 用于表示：
    - “Graph 已完成 intent 判定，可以继续回到旧 pipeline”
- `SearchLiteOrchestrator`
  - 已增加编排模式切换：
    - `search.lite.orchestrator.mode = pipeline | graph`
- `application.yml`
  - 新增：
    - `search.lite.orchestrator.mode`

### 13.1 为什么这一步不是“直接全量 Graph”

这是一次**渐进式接入**，而不是彻底替换。

当前的目标不是立刻把：

- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`
- `SQL_GENERATE`
- `SQL_EXECUTE`

全部迁进 Graph。

而是先让 Graph 接管**最有价值的第一段控制流**：

- `INTENT`

并在这个阶段完成：

- 非数据分析请求的提前停止
- 数据分析请求继续进入旧 pipeline

一句话理解：

> 当前是 Graph 与旧 pipeline 的“桥接运行阶段”。

### 13.2 当前真实执行链路是什么

当配置为：

- `search.lite.orchestrator.mode: graph`

时，当前执行链路变成：

```text
请求进入
-> Graph 执行 INTENT
-> Dispatcher 决定去向
   -> CHITCHAT: 直接结束
   -> DATA_ANALYSIS: 回到旧 pipeline，从 EVIDENCE 继续
```

这意味着：

- Graph 已经开始影响真实运行行为
- 但还没有完全替代现有 `SearchLiteOrchestrator`

### 13.3 当前为什么新增 `SearchLiteContinueGraphNode`

这是一个很重要的过渡设计。

如果直接让 `DATA_ANALYSIS -> END`，那 Graph 就无法告诉旧 orchestrator：

- “这条请求不是结束，而是应该继续跑后面的数据分析主链路”

因此新增：

- `SearchLiteContinueGraphNode`

用于在 graph 内显式写入一个 route marker：

- `graphRoute = continuePipeline`

这样外层 orchestrator 就知道：

- 可以从 index=1 开始继续旧 pipeline

### 13.4 当前 Graph 和旧 pipeline 如何配合

当前 `SearchLiteOrchestrator` 的行为是：

- `pipeline` 模式
  - 继续走原来的线性执行
- `graph` 模式
  - 先调用 `SearchLiteGraphService.runInitialGraph(...)`
  - Graph 会跑完当前最小图
  - 再根据返回的 route：
    - 继续旧 pipeline
    - 或直接结束

这一步的意义非常大，因为它说明：

- Graph 已经不仅是“架构实验”
- 而是已经成为真实运行路径的一部分

### 13.5 当前 Graph 模式下的限制

仍然需要明确：

- 现在只有 `INTENT` 真正接入了 Graph 主决策
- 还没有把 `EVIDENCE / SCHEMA / SQL` 真正迁入 Graph
- 还没有把 Graph 自己的 streaming output 接成最终 SSE 主机制

当前 Graph 模式仍然是：

- **Graph 负责前置路由**
- **旧 pipeline 负责后续业务阶段**

### 13.6 当前最重要的用户可见变化

这一步完成后，最关键的用户可见收益是：

> 当请求被判定为 `CHITCHAT` 时，系统不应该再继续进入召回阶段。

这正是当前 Graph 接入的第一价值点。

---

## 14. Step G6 完成内容（记录时间：2026-04-02）

本步骤目标：

- 解决 Graph 接入后在 WebFlux 线程上触发的阻塞错误
- 向 `management` 的 `sink + executor` 风格进一步靠拢
- 让 Graph 模式真正以“异步启动、异步发流”的方式参与运行

### 14.1 触发问题

在上一版实现中，Graph 模式会在 `reactor-http-nio-*` 线程上直接调用：

- `compiledGraph.invoke(...)`

这会触发：

- `block()/blockFirst()/blockLast() are blocking, which is not supported in thread reactor-http-nio-*`

根因不是业务逻辑错误，而是：

- `CompiledGraph.invoke(...)` 内部本身是同步/阻塞式实现
- WebFlux 的事件循环线程不允许执行这种阻塞调用

### 14.2 management 是怎么做的

`management` 在流式场景里，并不是直接在 controller 线程里执行 graph。

它采用的是：

- `Sinks.Many<ServerSentEvent<...>>`
- `ExecutorService`
- `CompletableFuture.runAsync(...)`
- service 异步启动 graph 处理
- controller 立即返回 `sink.asFlux()`

一句话理解：

> controller 只负责返回流，真正的 graph 执行在独立线程里启动。

### 14.3 当前 backend 在 G6 的实现

本步骤已完成：

- 在 `SearchLiteGraphConfiguration` 中新增 graph 专用执行器：
  - `searchLiteGraphExecutor`
- `SearchLiteGraphService`
  - 新增 `graphStreamProcess(...)`
  - 使用：
    - `Sinks.Many<SearchLiteMessage>`
    - `CompletableFuture.runAsync(..., executor)`
- `SearchLiteOrchestrator`
  - `graph` 模式不再直接同步调用 Graph
  - 而是：
    1. 创建 `sink`
    2. 调用 `graphService.graphStreamProcess(...)`
    3. 立即返回 `sink.asFlux()`

### 14.4 为什么这一步仍然不是完整的 management 版 graph stream

这里需要特别说明一个关键差异：

- `management` 的 graph node 本身会产出真正的 graph streaming output
- 当前 backend 的 graph node 还主要是：
  - 复用旧 step
  - 把 step 的 message 收集到 state 中

所以当前 G6 的实现虽然已经采用了：

- `sink + executor`

但 Graph 内部消息仍然是：

- **节点执行完成后批量发出**

而不是：

- **graph node 内部天然逐块实时流出**

换句话说：

> G6 已经把“线程模型”和“运行结构”对齐到 management 路线，但 Graph 内部的细粒度 streaming 仍是后续增强项。

### 14.5 G6 之后当前 Graph 模式的运行方式

当前 `graph` 模式可以理解为：

1. controller 发起 SSE 请求
2. orchestrator 创建 `sink`
3. graph service 在独立线程池中执行 Graph
4. 如果 route 是：
   - `continuePipeline`
     - 继续接旧 pipeline 的后续 step
   - 否则
     - 直接结束

这已经解决了最关键的问题：

- Graph 不再阻塞 WebFlux 事件循环线程

---

## 15. Step G7.1 完成内容（记录时间：2026-04-02）

本步骤目标：

- 把 `EvidenceFileStep` 正式包装成 Graph node
- 继续验证“先复用现有 step，再逐步 graph 化”的迁移路线可行
- 为后续 `G7.2` 的真实图路由改造准备节点地基

本步骤已完成：

- 新增：
  - `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\node\SearchLiteEvidenceGraphNode.java`
- 更新：
  - `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\SearchLiteGraphConfiguration.java`
  - 已把 `EVIDENCE_NODE` 注册进 graph
- 新增单测：
  - `D:\GitHub\DataAgent\data-agent-backend\src\test\java\com\alibaba\cloud\ai\dataagentbackend\lite\graph\node\SearchLiteEvidenceGraphNodeTest.java`

### 15.1 这一步做了什么

`SearchLiteEvidenceGraphNode` 延续了 G3 的桥接模式：

1. 从 `OverAllState` 还原 `SearchLiteState`
2. 创建 `SearchLiteContext`
3. 调用现有：
   - `EvidenceFileStep.run(...)`
4. 读取：
   - `updatedState`
   - `messages`
5. 再写回 graph state

这说明：

- `Evidence` 阶段已经可以像 `Intent / Result` 一样被 Graph 承接
- 后续 Graph 扩大覆盖范围时，不需要为每个阶段重写一套完全新的业务逻辑

### 15.2 当前为什么只注册 node，还没有改路由

这里是有意分成两步做的：

- **G7.1**
  - 先把 `Evidence` 包装成 node
- **G7.2**
  - 再修改图结构，让 `DATA_ANALYSIS` 真正从 `INTENT` 流向 `EVIDENCE`

这样做的好处是：

- 每一步职责清晰
- 一旦出问题，定位更容易
- 你也更容易学习：
  - “节点迁移”和“图路由迁移”其实是两件不同的事情

### 15.3 G7.1 完成后的当前状态

到这一步为止，Graph 世界里已经有 4 类节点：

- `Intent`
- `Continue`
- `Evidence`
- `Result`

但当前真实路由仍然还是：

- `INTENT -> CONTINUE / END`

也就是说：

- `Evidence` 节点**已经具备了**
- 但**还没开始被图真正走到**

这正是下一步 `G7.2` 要解决的事。

---

## 16. Step G7.2 完成内容（记录时间：2026-04-02）

本步骤目标：

- 修改图路由，让 `DATA_ANALYSIS` 请求真正经过 `EVIDENCE`
- 让 Graph 不再只是：
  - `INTENT -> CONTINUE / END`
- 而是开始接管更真实的主链路前半段

本步骤已完成：

- 更新 `SearchLiteIntentDispatcher`
  - `DATA_ANALYSIS` 不再路由到 `CONTINUE_NODE`
  - 改为路由到 `EVIDENCE_NODE`
- 更新 `SearchLiteGraphConfiguration`
  - 图结构变成：
    - `START -> INTENT`
    - `INTENT -> EVIDENCE / END`
    - `EVIDENCE -> CONTINUE`
    - `CONTINUE -> END`
- 更新 `SearchLiteOrchestrator`
  - Graph 模式下，如果 Graph 决定继续旧 pipeline
  - 现在会从 index=`2` 继续
  - 也就是跳过：
    - `INTENT`
    - `EVIDENCE`

### 16.1 这一步为什么关键

G5/G6 时，Graph 更像一个“前置路由器”：

- 只负责 `INTENT`
- 然后把真正的数据分析链路交回旧 pipeline

G7.2 完成后，Graph 的角色已经开始变化：

- 它不只负责“判断是不是数据分析”
- 还开始真正负责数据分析主链路中的第一段业务执行：
  - `EVIDENCE`

这一步意味着：

> Graph 已经开始承接真实业务节点，而不只是做一个入口判断。

### 16.2 当前图结构（G7.2 后）

现在的图可以理解为：

```text
START -> INTENT
INTENT -> EVIDENCE (when DATA_ANALYSIS)
INTENT -> END      (when CHITCHAT / empty)
EVIDENCE -> CONTINUE
CONTINUE -> END
```

### 16.3 为什么 orchestrator 现在要从 index=2 继续

旧 pipeline 的 step 顺序是：

1. `INTENT`
2. `EVIDENCE`
3. `SCHEMA`
4. `SCHEMA_RECALL`
5. `ENHANCE`
6. `SQL_GENERATE`
7. `SQL_EXECUTE`
8. `RESULT`

现在 Graph 已经接管了前两步：

- `INTENT`
- `EVIDENCE`

所以如果 Graph 执行完后还需要回到旧 pipeline，就必须从：

- `SCHEMA`

开始，也就是 index=`2`。

否则会重复执行 `EVIDENCE`。

### 16.4 G7.2 完成后的当前定位

现在 Graph 模式已经不是：

- “图判断一下，剩下都交给旧 pipeline”

而是：

- “图先跑 `INTENT + EVIDENCE`，再把后半段交给旧 pipeline”

所以从迁移进度上看，Graph 对主链路的接管范围已经进一步扩大了。

---

## 17. Step G7.3 完成内容（记录时间：2026-04-02）

本步骤目标：

- 把 `SCHEMA` 阶段也迁进 Graph
- 让 Graph 在 `DATA_ANALYSIS` 路径下继续承接真实业务节点
- 让旧 pipeline 的继续起点从 `SCHEMA_RECALL` 开始

本步骤已完成：

- 新增 `SearchLiteSchemaGraphNode`
  - 不直接依赖某个具体 schema 实现类
  - 而是从 Spring 注入的 `List<SearchLiteStep>` 中寻找 `stage() == SCHEMA` 的 step
  - 这样可以同时兼容：
    - `SchemaMysqlIntrospectStep`
    - `SchemaMockStep`
- 更新 `SearchLiteGraphConfiguration`
  - 注册 `SCHEMA_NODE`
  - 图结构改为：
    - `START -> INTENT`
    - `INTENT -> EVIDENCE / END`
    - `EVIDENCE -> SCHEMA`
    - `SCHEMA -> CONTINUE`
    - `CONTINUE -> END`
- 更新 `SearchLiteOrchestrator`
  - Graph 模式下继续旧 pipeline 的起点改为 index=`3`
  - 也就是从：
    - `SCHEMA_RECALL`
    - 开始继续
- 补充 `SearchLiteSchemaGraphNodeTest`

### 17.1 为什么 Schema node 不直接依赖具体类

这里特意没有把 Graph node 写成：

- 只依赖 `SchemaMysqlIntrospectStep`

原因是当前 lite backend 里，`SCHEMA` 阶段有两种实现：

- `SchemaMysqlIntrospectStep`
- `SchemaMockStep`

它们通过配置切换生效。

如果 Graph node 直接绑定某个具体类：

- 测试环境/演示环境切换 provider 时会更脆弱

所以这里采用了一个更通用的方式：

- 从全部 `SearchLiteStep` 里找 `stage() == SCHEMA` 的那个 step

这也是 Graph 迁移时很值得学习的一点：

> Graph node 不一定非要直接绑死到某个实现类，很多时候也可以绑到“阶段语义”。

### 17.2 当前图结构（G7.3 后）

现在的图可以理解为：

```text
START -> INTENT
INTENT -> EVIDENCE (when DATA_ANALYSIS)
INTENT -> END      (when CHITCHAT / empty)
EVIDENCE -> SCHEMA
SCHEMA -> CONTINUE
CONTINUE -> END
```

### 17.3 为什么 orchestrator 现在要从 index=3 继续

旧 pipeline 顺序是：

1. `INTENT`
2. `EVIDENCE`
3. `SCHEMA`
4. `SCHEMA_RECALL`
5. `ENHANCE`
6. `SQL_GENERATE`
7. `SQL_EXECUTE`
8. `RESULT`

现在 Graph 已经接管了前三步：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`

所以如果 Graph 执行完后要回旧 pipeline，就必须从：

- `SCHEMA_RECALL`

开始，也就是 index=`3`。

### 17.4 G7.3 完成后的迁移进度

到这一步为止，Graph 已经接管了主链路前 3 个阶段：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`

这意味着 Graph 已经不只是做“入口判断 + 一点前置处理”，
而是在逐步吃掉原先线性 pipeline 的主干。

---

## 18. Step G7.4 完成内容（记录时间：2026-04-02）

本步骤目标：

- 把 `SCHEMA_RECALL` 也迁进 Graph
- 让 Graph 在 SQL 生成前继续承接关键的 schema 聚焦阶段
- 让旧 pipeline 的继续起点再往后挪到 `ENHANCE`

本步骤已完成：

- 新增 `SearchLiteSchemaRecallGraphNode`
  - 和 `Schema` node 一样，不绑定具体实现类
  - 而是从 `List<SearchLiteStep>` 中寻找 `stage() == SCHEMA_RECALL` 的 step
- 更新 `SearchLiteGraphConfiguration`
  - 注册 `SCHEMA_RECALL_NODE`
  - 图结构改为：
    - `START -> INTENT`
    - `INTENT -> EVIDENCE / END`
    - `EVIDENCE -> SCHEMA`
    - `SCHEMA -> SCHEMA_RECALL`
    - `SCHEMA_RECALL -> CONTINUE`
    - `CONTINUE -> END`
- 更新 `SearchLiteOrchestrator`
  - Graph 模式下继续旧 pipeline 的起点改为 index=`4`
  - 也就是从：
    - `ENHANCE`
    - 开始继续
- 补充 `SearchLiteSchemaRecallGraphNodeTest`

### 18.1 为什么 Schema recall 也值得尽早迁进 Graph

`SCHEMA_RECALL` 和 `SCHEMA` 不一样，它不是“把数据库结构拿出来”，
而是：

- 根据当前 query 和 evidence
- 选择真正和本次问题相关的表/列

这一步其实对后续：

- `ENHANCE`
- `SQL_GENERATE`

的输入质量非常关键。

所以把它迁进 Graph 的价值很高，因为它已经是“前置上下文构造”中的核心环节了。

### 18.2 当前图结构（G7.4 后）

现在的图可以理解为：

```text
START -> INTENT
INTENT -> EVIDENCE (when DATA_ANALYSIS)
INTENT -> END      (when CHITCHAT / empty)
EVIDENCE -> SCHEMA
SCHEMA -> SCHEMA_RECALL
SCHEMA_RECALL -> CONTINUE
CONTINUE -> END
```

### 18.3 为什么 orchestrator 现在要从 index=4 继续

旧 pipeline 顺序是：

1. `INTENT`
2. `EVIDENCE`
3. `SCHEMA`
4. `SCHEMA_RECALL`
5. `ENHANCE`
6. `SQL_GENERATE`
7. `SQL_EXECUTE`
8. `RESULT`

现在 Graph 已经接管了前四步：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`

所以 Graph 执行完后回旧 pipeline 时，必须从：

- `ENHANCE`

开始，也就是 index=`4`。

### 18.4 G7.4 完成后的迁移进度

到这一步为止，Graph 已经接管了主链路前 4 个阶段：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`

也就是说，Graph 现在已经覆盖了“进入 SQL 生成前的主要上下文准备链路”。

---

## 19. Step G7.5 完成内容（记录时间：2026-04-02）

本步骤目标：

- 把 `ENHANCE` 也迁进 Graph
- 让 Graph 把 SQL 生成前的 query 规范化阶段也接管掉
- 让旧 pipeline 的继续起点再往后挪到 `SQL_GENERATE`

本步骤已完成：

- 新增 `SearchLiteEnhanceGraphNode`
  - 延续前面的统一迁移方式
  - 从 `List<SearchLiteStep>` 中寻找 `stage() == ENHANCE` 的 step
- 更新 `SearchLiteGraphConfiguration`
  - 注册 `ENHANCE_NODE`
  - 图结构改为：
    - `START -> INTENT`
    - `INTENT -> EVIDENCE / END`
    - `EVIDENCE -> SCHEMA`
    - `SCHEMA -> SCHEMA_RECALL`
    - `SCHEMA_RECALL -> ENHANCE`
    - `ENHANCE -> CONTINUE`
    - `CONTINUE -> END`
- 更新 `SearchLiteOrchestrator`
  - Graph 模式下继续旧 pipeline 的起点改为 index=`5`
  - 也就是从：
    - `SQL_GENERATE`
    - 开始继续
- 补充 `SearchLiteEnhanceGraphNodeTest`

### 19.1 为什么 Enhance 也适合迁进 Graph

`ENHANCE` 负责的是：

- 把原始 query 规范化为更明确的 `canonicalQuery`
- 补充 `expandedQueries`

这一步和前面的 `EVIDENCE / SCHEMA / SCHEMA_RECALL` 一样，
都属于“SQL 生成前的上下文准备阶段”。

所以把它迁进 Graph 很自然，因为这会让：

- 前置理解
- 证据召回
- schema 聚焦
- query 规范化

形成一条更完整的 Graph 前半链路。

### 19.2 当前图结构（G7.5 后）

现在的图可以理解为：

```text
START -> INTENT
INTENT -> EVIDENCE (when DATA_ANALYSIS)
INTENT -> END      (when CHITCHAT / empty)
EVIDENCE -> SCHEMA
SCHEMA -> SCHEMA_RECALL
SCHEMA_RECALL -> ENHANCE
ENHANCE -> CONTINUE
CONTINUE -> END
```

### 19.3 为什么 orchestrator 现在要从 index=5 继续

旧 pipeline 顺序是：

1. `INTENT`
2. `EVIDENCE`
3. `SCHEMA`
4. `SCHEMA_RECALL`
5. `ENHANCE`
6. `SQL_GENERATE`
7. `SQL_EXECUTE`
8. `RESULT`

现在 Graph 已经接管了前五步：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`

所以 Graph 执行完后回旧 pipeline 时，必须从：

- `SQL_GENERATE`

开始，也就是 index=`5`。

### 19.4 G7.5 完成后的迁移进度

到这一步为止，Graph 已经接管了 SQL 生成前的完整准备链路：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`

这意味着后续如果要继续迁移：

- `SQL_GENERATE`
- `SQL_EXECUTE`
- `RESULT`

Graph 就会开始真正接近“完整主链路编排”。

---

## 20. Step G7.6 完成内容（记录时间：2026-04-02）

本步骤目标：

- 把 `SQL_GENERATE` 迁进 Graph
- 让 Graph 开始承接真正的“核心结果产出”阶段
- 让旧 pipeline 的继续起点再往后挪到 `SQL_EXECUTE`

本步骤已完成：

- 新增 `SearchLiteSqlGenerateGraphNode`
  - 继续沿用按阶段语义寻找 step 的迁移方式
  - 从 `List<SearchLiteStep>` 中寻找 `stage() == SQL_GENERATE` 的 step
- 更新 `SearchLiteGraphConfiguration`
  - 注册 `SQL_GENERATE_NODE`
  - 图结构改为：
    - `START -> INTENT`
    - `INTENT -> EVIDENCE / END`
    - `EVIDENCE -> SCHEMA`
    - `SCHEMA -> SCHEMA_RECALL`
    - `SCHEMA_RECALL -> ENHANCE`
    - `ENHANCE -> SQL_GENERATE`
    - `SQL_GENERATE -> CONTINUE`
    - `CONTINUE -> END`
- 更新 `SearchLiteOrchestrator`
  - Graph 模式下继续旧 pipeline 的起点改为 index=`6`
  - 也就是从：
    - `SQL_EXECUTE`
    - 开始继续
- 补充 `SearchLiteSqlGenerateGraphNodeTest`

### 20.1 为什么 SQL generate 是一个迁移分水岭

前面的：

- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`

都还是“为 SQL 生成做准备”。

而 `SQL_GENERATE` 不一样，它已经真正开始产出：

- 面向数据库执行的核心结果

所以把它迁进 Graph 后，Graph 的角色发生了进一步变化：

- 不再只是“前置理解与准备链路”
- 而是开始接管“核心产出链路”本身

### 20.2 当前图结构（G7.6 后）

现在的图可以理解为：

```text
START -> INTENT
INTENT -> EVIDENCE (when DATA_ANALYSIS)
INTENT -> END      (when CHITCHAT / empty)
EVIDENCE -> SCHEMA
SCHEMA -> SCHEMA_RECALL
SCHEMA_RECALL -> ENHANCE
ENHANCE -> SQL_GENERATE
SQL_GENERATE -> CONTINUE
CONTINUE -> END
```

### 20.3 为什么 orchestrator 现在要从 index=6 继续

旧 pipeline 顺序是：

1. `INTENT`
2. `EVIDENCE`
3. `SCHEMA`
4. `SCHEMA_RECALL`
5. `ENHANCE`
6. `SQL_GENERATE`
7. `SQL_EXECUTE`
8. `RESULT`

现在 Graph 已经接管了前六步：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`
- `SQL_GENERATE`

所以 Graph 执行完后回旧 pipeline 时，必须从：

- `SQL_EXECUTE`

开始，也就是 index=`6`。

### 20.4 G7.6 完成后的迁移进度

到这一步为止，Graph 已经接管了：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`
- `SQL_GENERATE`

现在旧 pipeline 只剩下最后两段：

- `SQL_EXECUTE`
- `RESULT`

也就是说，Graph 已经非常接近完整主链路编排了。

---

## 21. Step G7.7 完成内容（记录时间：2026-04-02）

本步骤目标：

- 把 `SQL_EXECUTE` 迁进 Graph
- 让 Graph 接管真正的数据库执行阶段
- 让旧 pipeline 的继续起点再往后挪到 `RESULT`

本步骤已完成：

- 新增 `SearchLiteSqlExecuteGraphNode`
  - 继续沿用按阶段语义寻找 step 的迁移方式
  - 从 `List<SearchLiteStep>` 中寻找 `stage() == SQL_EXECUTE` 的 step
  - 这样同时兼容：
    - `SqlExecuteJdbcStep`
    - `SqlExecuteMockStep`
- 更新 `SearchLiteGraphConfiguration`
  - 注册 `SQL_EXECUTE_NODE`
  - 图结构改为：
    - `START -> INTENT`
    - `INTENT -> EVIDENCE / END`
    - `EVIDENCE -> SCHEMA`
    - `SCHEMA -> SCHEMA_RECALL`
    - `SCHEMA_RECALL -> ENHANCE`
    - `ENHANCE -> SQL_GENERATE`
    - `SQL_GENERATE -> SQL_EXECUTE`
    - `SQL_EXECUTE -> CONTINUE`
    - `CONTINUE -> END`
- 更新 `SearchLiteOrchestrator`
  - Graph 模式下继续旧 pipeline 的起点改为 index=`7`
  - 也就是从：
    - `RESULT`
    - 开始继续
- 补充 `SearchLiteSqlExecuteGraphNodeTest`

### 21.1 为什么 SQL execute 也必须按阶段语义绑定

和 `SCHEMA`、`SQL_EXECUTE` 相关的阶段一样，当前 lite backend 中也有两套执行实现：

- `SqlExecuteJdbcStep`
- `SqlExecuteMockStep`

它们通过配置切换：

- 真实数据库执行
- 演示/离线 mock 执行

所以 Graph node 如果绑定到某个具体类，会让 Graph 编排对 provider 切换不友好。

因此这里继续采用统一方式：

- 绑定到 `stage() == SQL_EXECUTE`

这也是当前整套 Graph 迁移最一致的一条经验：

> Graph node 优先绑定“阶段语义”，而不是具体 provider 实现。

### 21.2 当前图结构（G7.7 后）

现在的图可以理解为：

```text
START -> INTENT
INTENT -> EVIDENCE (when DATA_ANALYSIS)
INTENT -> END      (when CHITCHAT / empty)
EVIDENCE -> SCHEMA
SCHEMA -> SCHEMA_RECALL
SCHEMA_RECALL -> ENHANCE
ENHANCE -> SQL_GENERATE
SQL_GENERATE -> SQL_EXECUTE
SQL_EXECUTE -> CONTINUE
CONTINUE -> END
```

### 21.3 为什么 orchestrator 现在要从 index=7 继续

旧 pipeline 顺序是：

1. `INTENT`
2. `EVIDENCE`
3. `SCHEMA`
4. `SCHEMA_RECALL`
5. `ENHANCE`
6. `SQL_GENERATE`
7. `SQL_EXECUTE`
8. `RESULT`

现在 Graph 已经接管了前七步：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`
- `SQL_GENERATE`
- `SQL_EXECUTE`

所以 Graph 执行完后回旧 pipeline 时，必须从：

- `RESULT`

开始，也就是 index=`7`。

### 21.4 G7.7 完成后的迁移进度

到这一步为止，Graph 已经接管了除 `RESULT` 外的全部主链路阶段：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`
- `SQL_GENERATE`
- `SQL_EXECUTE`

现在旧 pipeline 只剩最后一段：

- `RESULT`

也就是说，Graph 已经到达“几乎完整主链路编排”的状态。

---

## 22. Step G7.8 完成内容（记录时间：2026-04-02）

本步骤目标：

- 把 `RESULT` 也彻底收进 Graph
- 让数据分析主链路不再回旧 pipeline
- 让 Graph 真正完成从 `INTENT` 到 `RESULT` 的完整闭环

本步骤已完成：

- 更新 `SearchLiteGraphConfiguration`
  - 正常数据分析路径不再经过 `CONTINUE_NODE`
  - 图结构改为：
    - `START -> INTENT`
    - `INTENT -> EVIDENCE / END`
    - `EVIDENCE -> SCHEMA`
    - `SCHEMA -> SCHEMA_RECALL`
    - `SCHEMA_RECALL -> ENHANCE`
    - `ENHANCE -> SQL_GENERATE`
    - `SQL_GENERATE -> SQL_EXECUTE`
    - `SQL_EXECUTE -> RESULT`
    - `RESULT -> END`
- 更新 `SearchLiteGraphService`
  - `graphStreamProcess(...)` 不再接 continuation callback
  - Graph 执行结束后：
    - 如果已经有 graph messages，就直接 complete
    - 如果没有 message（例如 `CHITCHAT -> END`），再补一个简短完成消息
- 更新 `SearchLiteOrchestrator`
  - graph 模式下不再回旧 pipeline
  - 请求直接完整走 Graph

### 22.1 这一步为什么是迁移闭环

G7.1 ~ G7.7 都还是“逐步接管主链路”，但仍然存在一个共同点：

- Graph 跑到一半
- 再回旧 pipeline 继续

而 G7.8 之后，这个特点发生了根本变化：

- 对于正常的数据分析主链路，Graph 已经可以从头跑到尾
- 不再需要回旧 pipeline

这意味着：

> Graph 不再只是一个“前半段 orchestrator”，而是已经成为完整主编排器。

### 22.2 当前图结构（G7.8 后）

现在的图可以理解为：

```text
START -> INTENT
INTENT -> EVIDENCE (when DATA_ANALYSIS)
INTENT -> END      (when CHITCHAT / empty)
EVIDENCE -> SCHEMA
SCHEMA -> SCHEMA_RECALL
SCHEMA_RECALL -> ENHANCE
ENHANCE -> SQL_GENERATE
SQL_GENERATE -> SQL_EXECUTE
SQL_EXECUTE -> RESULT
RESULT -> END
```

### 22.3 现在 `CONTINUE_NODE` 的地位发生了什么变化

在 G7.1 ~ G7.7 阶段，`CONTINUE_NODE` 的作用是：

- 告诉 orchestrator：
  - “Graph 到这里先停一下，回旧 pipeline 继续跑”

而 G7.8 之后：

- 正常数据分析主链路已经不再依赖它

也就是说：

- `CONTINUE_NODE` 不再是当前主路径的一部分

这个变化很重要，因为它标志着：

- Graph 已经从“过渡式接入”进入“主链路完整接管”阶段

### 22.4 G7.8 完成后的迁移状态

到这一步为止，Graph 已经完整接管了 `search-lite` 的主链路：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SCHEMA_RECALL`
- `ENHANCE`
- `SQL_GENERATE`
- `SQL_EXECUTE`
- `RESULT`

也就是说，当前 `graph` 模式下：

- 数据分析请求已经完全走图编排
- `CHITCHAT` 等非数据分析请求会在 `INTENT` 后直接结束

这就是我们这轮迁移的第一个完整闭环。

---

## 23. Graph 消息回放编码问题记录（记录时间：2026-04-02）

在 G7.8 之后，Graph 主链路虽然已经可以完整跑通，但实际联调时暴露了一个很典型的问题：

- WebFlux SSE 在回放 Graph 收集到的整批 `SearchLiteMessage` 时
- 报出了 `EncodingException`
- 典型错误信息是：
  - `JSON encoding error: object is not an instance of declaring class`

### 23.1 问题出现的位置

这个问题不是出在：

- `INTENT`
- `EVIDENCE`
- `SCHEMA`
- `SQL_GENERATE`

这些业务逻辑本身。

从日志看，真正的链路其实已经跑完了，甚至 `RESULT` 阶段也完成了。

问题出在最后一步：

- Graph 把所有阶段消息暂存在 state 中
- Graph 结束后统一回放这些消息给 SSE
- 这时其中某些 message 的 `payload` 已经不再是 WebFlux/Jackson 最稳妥的直接可编码对象

### 23.2 为什么 Graph 模式更容易暴露这个问题

旧 pipeline 模式下：

- message 是每个 step 直接产出后马上往外发

而 Graph 模式下当前还是一个“过渡式实现”：

- 先在 node 内部把 message 收集起来
- 再放进 Graph state
- Graph 全部结束后，再统一 emit

因此 message/payload 在 Graph state 中间流转一遍后，
更容易出现：

- 运行时类型不稳定
- 反射/record accessor 对不上实例
- Jackson 在编码阶段才报错

### 23.3 第一版修复方式

在 `SearchLiteGraphService` 中增加了统一“消息规范化”逻辑：

- 对 `GRAPH_MESSAGES` 中取出的每一条消息统一做一次 `normalize`
- 对 message 本身：
  - 如果不是直接的 `SearchLiteMessage`，先通过 `ObjectMapper.convertValue(..., SearchLiteMessage.class)` 转换
- 对 payload：
  - 再通过 `ObjectMapper.convertValue(payload, Object.class)` 转成 Jackson 友好的结构

这样做的目的不是“改变业务内容”，而是：

- 把 Graph state 中流转过的对象
- 重新压平成更稳定的 `Map/List/String/Number/...` 结构

从而避免 SSE 编码阶段再踩到反射类型问题。

### 23.4 为什么第一版修复还不够

后续联调时，我们又遇到了更具体的一条错误：

- `focusedTables -> SchemaTable -> columns -> LinkedHashMap`

这说明第一版里的：

- `ObjectMapper.convertValue(payload, Object.class)`

并没有强制把所有嵌套层都彻底压平成普通 JSON 结构。

原因是：

- 当目标类型写成 `Object.class` 时
- Jackson 有时会保留一部分原始 record / POJO 结构
- 最终形成“外层还是 record，内层已经是 map”的混合对象

而这种混合对象在 SSE 最终编码时就很危险，因为反射访问器会发现：

- 声明类型和实际实例类型不匹配

于是报出：

- `object is not an instance of declaring class`

### 23.5 第二版修复方式

第二版修复改成了更彻底的“先序列化，再反序列化”：

- 先 `writeValueAsBytes(payload)`
- 再 `readValue(..., Object.class)`

也就是强制让 payload 完整经过一次 JSON 边界，
最终落成更稳定的：

- `Map`
- `List`
- `String`
- `Number`
- `Boolean`
- `null`

如果这个过程失败，再回退到：

- `valueToTree(...) + convertValue(..., Object.class)`

这样处理后，Graph state 中的 payload 在回放给 SSE 前，
会更接近真正的 JSON 数据，而不是运行时对象和 map 的混合结构。

### 23.6 对照 management 后得到的进一步启发

继续对照 `management` 后，我们发现一个更本质的差别：

- `management` 不会把一整批复杂的业务消息对象长期塞进 graph state
- 它更接近：
  - graph 节点输出 `StreamingOutput`
  - service 直接把轻量响应对象写到 `sink`

而当前 lite backend 的过渡式实现是：

- node 内部先收集 `SearchLiteMessage`
- 放进 `GRAPH_MESSAGES`
- Graph 全部结束后统一回放

这意味着当前 lite graph 实现天然更容易遇到：

- payload 类型不稳定
- record / map / list 混合嵌套
- 最终 SSE 编码时才暴露错误

因此，当前修复虽然已经把 payload 做了更深层的 JSON 化规整，
但从长期架构上看，更值得继续向 management 靠拢的一点是：

> 尽量减少“把复杂消息对象长期存进 graph state 再统一回放”这种模式。

也就是说，后续更理想的方向是：

- Graph 更偏重状态流转
- 消息更偏重流式直接输出

### 23.7 为什么第三版修复又补了“递归深度规整”

继续联调后我们发现，单纯：

- `writeValueAsBytes(payload) -> readValue(..., Object.class)`

仍然可能在某些混合对象上失败。

因此第三版修复又补了一层更稳妥的递归规整：

- `Map`：逐项递归转
- `List`：逐项递归转
- 基础类型：直接保留
- 其他对象：
  - 优先尝试完整 JSON 序列化
  - 失败后尝试 `convertValue(..., Map.class)`
  - 再失败才退回 `valueToTree(...)`
  - 最后兜底成 `String`

这使得像：

- `focusedTables -> SchemaTable -> columns -> LinkedHashMap`

这种混合结构，也会在真正进入 SSE 编码前被压平成普通 JSON 友好的结构。

### 23.8 这件事对学习 Graph 很有价值

这说明一个很重要的事实：

> Graph 编排不只是“节点怎么连起来”，还要考虑“状态里流转的对象是不是适合跨阶段、跨线程、跨框架边界再被重新编码”。

也就是说：

- Graph state 最适合放“稳定、扁平、可序列化”的数据
- 不太适合长期原样保存那些复杂运行时对象

这也是后续如果我们继续往更完整的 graph streaming 演进时，需要持续优化的一点。
