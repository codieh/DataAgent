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

---

## 24. Step G8.1 完成内容（记录时间：2026-04-02）

本步骤目标：

- 开始把 Graph 的消息机制向 `management` 靠拢
- 减少“先把复杂消息塞进 graph state，再统一回放”的依赖
- 先做一层稳妥演进：让 graph node 在 step 执行后直接把消息推到 sink

本步骤已完成：

- 新增 `SearchLiteGraphMessageEmitter`
  - 用 `threadId -> sink` 的注册表维护当前 graph 请求对应的 SSE sink
- 更新 `SearchLiteGraphService`
  - 在 `graphStreamProcess(...)` 开始时注册 sink
  - 结束时注销 sink
- 更新 `SearchLiteStepGraphNodeSupport`
  - step 执行后，如果当前 threadId 已注册 sink
  - 则直接把 `stepMessages` emit 到 sink
  - 只有在没有可用 sink 时，才退回到旧的 `GRAPH_MESSAGES` 暂存逻辑
- 更新所有 graph node
  - 现在统一通过 `SearchLiteGraphMessageEmitter` 走消息直推能力

### 24.1 这一步和 management 的关系

这一步还不是完全等同于 `management` 的 streaming 模式。

`management` 更进一步，它是：

- 节点内部直接产生 `StreamingOutput`
- service 订阅 graph stream 后立刻往 sink 推送

而当前 lite backend 的 G8.1 仍然保留了一个过渡特征：

- step 内部消息先 `collectList().block()`
- 但 collect 完后不再优先塞进 graph state
- 而是优先直接 emit 到 sink

所以这一步可以理解为：

> 还没做到“节点内逐 delta 直出”，但已经做到“消息优先直接输出，而不是优先塞回 graph state”。

### 24.2 为什么这一步很重要

它直接减少了当前最脆弱的一环：

- `SearchLiteMessage` 中带复杂 payload
- payload 在 graph state 里走一圈
- 再统一回放时发生序列化问题

G8.1 之后，这个风险显著下降，因为：

- 大部分主链路消息不再依赖 `GRAPH_MESSAGES`
- 而是在节点完成后直接推送给 SSE sink

### 24.3 这一步之后的架构含义

这说明 Graph 模式的职责开始变得更清晰：

- Graph state：更偏向保存业务状态
- sink：更偏向承担消息输出

这正是后续继续向 `management` 靠拢的基础。

---

## 25. Step G8.2 完成内容（记录时间：2026-04-02）

本步骤目标：

- 把当前“step 执行后如何把结果变成 graph 输出”的逻辑再抽一层
- 让 graph node 的职责更纯，只负责执行业务
- 让“结果适配 + 消息输出”更接近 `management` 里 `FluxUtil` 那种独立适配层思路

本步骤已完成：

- 新增 `SearchLiteGraphStepOutputAdapter`
  - 专门负责：
    - 聚合 `SearchLiteStepResult`
    - 决定是直接 emit 到 sink，还是回退到 `GRAPH_MESSAGES`
    - 把更新后的 `SearchLiteState` 再映射回 graph state
- 更新 `SearchLiteStepGraphNodeSupport`
  - 不再自己处理：
    - `messages().collectList()`
    - `updatedState().block()`
    - 直推还是暂存的决策
  - 这些都交给 `SearchLiteGraphStepOutputAdapter`
- 更新所有 graph node
  - 现在统一依赖 `SearchLiteGraphStepOutputAdapter`
  - node 本身只做：
    - 选中正确的 step
    - 调 `executeStep(...)`

### 25.1 这一步和 G8.1 的区别

G8.1 做的是：

- 行为层面的改变
  - “消息优先直推 sink，而不是优先塞回 graph state”

G8.2 做的是：

- 结构层面的改变
  - 把“step 输出如何适配成 graph 输出”抽成独立组件

所以 G8.2 的价值不只是代码更整洁，而是：

> graph node、step output adapter、message emitter 三者的职责开始分离了。

### 25.2 和 management 的相似点在哪里

虽然当前 lite backend 还没做到 `management` 那种：

- 节点直接产出 `StreamingOutput`
- service 订阅 graph stream 即时推送

但 G8.2 已经在结构上开始对齐它的思想：

- 节点不直接承担所有输出细节
- 输出适配被抽到专门层里

这和 `management` 中：

- node 负责业务
- `FluxUtil` 负责把业务输出适配成 graph streaming response

是同一类思路。

### 25.3 这一步之后的收益

G8.2 完成后，我们后面如果要继续往真正 streaming 演进，会更容易：

- 继续替换 adapter 内部实现
- 逐步减少 `collectList().block()`
- 最后把 step 输出进一步改造成更贴近 graph-native 的流式输出

也就是说，这一步是一次很重要的“中间层抽象”。

---

## 26. Step G8.3 完成内容（记录时间：2026-04-02）

本步骤目标：

- 开始减少 `collectList().block()` 这类“先收齐再发”的行为
- 先把 graph 输出路径中的“消息”这一条改成更接近 streaming
- 让用户在 graph 模式下更早看到节点输出

本步骤已完成：

- 更新 `SearchLiteGraphMessageEmitter`
  - 新增：
    - `hasSink(threadId)`
    - `emitOne(threadId, message)`
- 更新 `SearchLiteGraphStepOutputAdapter`
  - 当当前 threadId 已注册 sink 时：
    - 不再 `collectList().block()`
    - 而是对 `stepResult.messages()` 逐条 `doOnNext(...emitOne...)`
    - 然后等待消息流完成
  - 只有在没有 sink 的兜底场景下，才继续保留：
    - `collectList().block()`
    - 放入 `GRAPH_MESSAGES`

### 26.1 这一步具体减少了什么阻塞

G8.2 之前，adapter 里是：

- `updatedState().block()`
- `messages().collectList().block()`

也就是说：

- 消息必须先全部收齐
- 才会一次性发给用户

G8.3 之后，至少在有 sink 的主路径下：

- message 不再先收齐
- 而是边从 `Flux<SearchLiteMessage>` 里取出
- 边直接推给 sink

这意味着：

- 用户能更早看到节点输出
- graph 消息路径更接近真实 streaming

### 26.2 为什么这一步还不是完全 non-blocking

需要很诚实地说，这一步还不是“彻底无阻塞”的最终形态。

因为当前 adapter 里仍然保留了一处：

- `updatedState().defaultIfEmpty(...).block()`

这是因为当前 graph node 的 `apply(...)` 仍然是同步返回 `Map<String, Object>`，
所以在不彻底改造 node contract 的前提下，我们仍然需要等到 state 更新完成，
才能把更新后的 graph state 返回给图继续往下走。

所以 G8.3 更准确地说是：

> 先把“消息输出”这条线从“收齐后回放”改成“逐条直出”，而不是一步到位把整个 node 都改成完全异步。

### 26.3 这一步和 management 的距离

相比 `management`，我们现在仍然还差一层：

- `management` 更像是节点天然产出 graph streaming output
- 而当前 lite backend 还是：
  - step 先产出 Reactor 消息流
  - adapter 再把它桥接到 sink

但 G8.3 至少已经完成了一个很关键的转变：

- **消息输出不再优先依赖 `collectList().block()`**

这让后续继续往真正的 graph-native streaming 演进时，阻力小了很多。

---

## 27. Step G8.4 完成内容（记录时间：2026-04-03）

本步骤目标：

- 继续减少 `GRAPH_MESSAGES` 在主路径中的存在感
- 让 graph state 更像“状态容器”，而不是“消息暂存区”
- 进一步向 `management` 的“消息直接流向 sink”靠拢

本步骤已完成：

- 更新 `SearchLiteGraphStepOutputAdapter`
  - 新增：
    - `hasLiveSink(threadId)`
  - 当当前请求已经绑定 live sink 时：
    - 继续逐条直推 `stepResult.messages()`
    - 同时显式从 `mappedState` 中移除 `GRAPH_MESSAGES`
- 更新 `SearchLiteStepGraphNodeSupport`
  - 只有在 **没有 live sink** 的兜底场景下，才读取 graph state 中已有的 `GRAPH_MESSAGES`
  - 对于正常的 SSE 主路径：
    - 不再先把旧消息读出来
    - 也不再让新的 graph state 继续携带这批消息

### 27.1 这一步具体减少了什么耦合

G8.3 之后，虽然消息已经优先直推 sink 了，但 graph node 仍然还会做一件多余的事：

- 每次执行 step 前，先从 graph state 里读取 `GRAPH_MESSAGES`

这意味着即使主路径已经不需要“消息回放”，
node 仍然会把自己和 `GRAPH_MESSAGES` 这个兼容字段绑定在一起。

G8.4 做的事情就是把这层耦合继续拆掉：

- **有 sink 的时候，node 只关心状态推进和消息直推**
- **没有 sink 的时候，才回退到旧的消息暂存机制**

### 27.2 为什么这一步重要

这一步看起来像“小优化”，但其实非常关键。

因为它让 graph state 的职责进一步收敛成：

- 保存业务状态
  - `intentClassification`
  - `schemaText`
  - `sql`
  - `rows`
  - `resultSummary`

而不是继续承担：

- “顺带缓存所有中间消息”

这正是我们向 `management` 靠拢时最需要的方向：

> **图负责状态推进，sink 负责消息流出。**

### 27.3 G8.4 完成后的当前形态

到这一步，当前 graph 输出机制可以这样理解：

- **主路径（SSE + live sink）**
  - 节点消息优先逐条直推到 sink
  - graph state 不再继续携带 `GRAPH_MESSAGES`
- **兜底路径（无 sink / 直接调用）**
  - 仍然允许使用 `GRAPH_MESSAGES`
  - 以便保留兼容性和调试能力

所以 G8.4 并不是完全移除了 `GRAPH_MESSAGES`，
而是把它降级成了一个：

- **兼容层字段**

而不再是主输出通道。

---

## 28. Step G8.5 完成内容（记录时间：2026-04-03）

本步骤目标：

- 让 `SearchLiteGraphService` 的主路径也进一步摆脱 `GRAPH_MESSAGES`
- 避免 graph 结束后再做一次“整批消息回放”
- 把 graph service 的职责更明确地拆成：
  - 调图拿最终 state
  - 在需要时才读取兜底消息

本步骤已完成：

- 更新 `SearchLiteGraphService`
  - 抽出：
    - `invokeFinalState(...)`
    - `toExecutionResult(...)`
  - `graphStreamProcess(...)` 的主路径现在直接：
    - 调图得到最终 `OverAllState`
    - 只还原 `SearchLiteState` 和 `route`
    - **不再读取 `GRAPH_MESSAGES`**
- `runInitialGraph(...)` 仍然保留
  - 但它现在被明确收敛为：
    - **同步/兜底路径**
    - 如果未来需要在无 sink 场景下直接拿 graph 结果，仍然可以继续读取并规范化 `GRAPH_MESSAGES`

### 28.1 这一步具体减少了什么

G8.4 之后，node 侧已经做到：

- 主路径下优先直推 sink
- graph state 不再继续携带 `GRAPH_MESSAGES`

但 service 侧仍然保留了一个旧思维：

- graph 跑完后，默认还会去 final state 里读 `GRAPH_MESSAGES`
- 然后再尝试 `emitMessages(...)`

这会带来两个问题：

- 即使主路径已经不需要“消息回放”，service 仍然会保留这条逻辑
- 代码结构上会让人误以为：
  - graph 主路径还是依赖 `GRAPH_MESSAGES`

G8.5 把这层历史包袱继续拆掉了。

### 28.2 现在 service 的两条路径

到这一步，`SearchLiteGraphService` 已经更清晰地分成了两类用途：

- **主路径：`graphStreamProcess(...)`**
  - 面向 SSE + live sink
  - 只关心：
    - graph 最终 state
    - route
    - 兜底完成/错误消息
  - 不再读取 `GRAPH_MESSAGES`

- **兼容路径：`runInitialGraph(...)`**
  - 面向同步调用/调试/兜底
  - 仍然可以把 `GRAPH_MESSAGES` 读出来并做规范化

### 28.3 这一步和 management 的关系

这一步很接近 `management` 的一个重要思想：

> **主流式链路不要在 graph 结束后再做消息回放。**

虽然我们现在还没有完全做到 `compiledGraph.stream(...) + StreamingOutput`，
但至少在 service 这一层，主路径已经开始更像：

- 图负责推进状态
- sink 负责承接消息

而不是：

- 图先把消息都存起来
- service 再统一拿出来回放

---

## 29. Step G8.6 完成内容（记录时间：2026-04-03）

本步骤目标：

- 把消息规范化逻辑从 `SearchLiteGraphService` 里继续抽出来
- 让“直接发到 sink”和“兜底读取 `GRAPH_MESSAGES`”共用同一套消息归一化规则
- 继续减少 Graph service 中与消息序列化细节的耦合

本步骤已完成：

- 新增：
  - `SearchLiteGraphMessageNormalizer`
- 更新：
  - `SearchLiteGraphMessageEmitter`
  - `SearchLiteGraphService`

### 29.1 这一步具体做了什么

在 G8.5 之前，消息规范化逻辑仍然主要放在 `SearchLiteGraphService` 里：

- `normalizeMessages(...)`
- `normalizeMessage(...)`
- `normalizePayload(...)`

这会带来一个结构问题：

- **service 既负责调图、拿最终 state，又负责处理消息序列化细节**

而实际在当前架构里，真正需要消息规范化的地方有两处：

- **主路径**
  - 节点消息直接推给 sink
- **兜底路径**
  - 从 `GRAPH_MESSAGES` 读回旧消息再返回

所以 G8.6 把消息规范化继续抽成独立组件：

- `SearchLiteGraphMessageNormalizer`

### 29.2 现在三层职责如何分工

到这一步，graph 消息相关职责已经更清楚了：

- `SearchLiteGraphMessageNormalizer`
  - 负责把消息和 payload 压平成稳定的 JSON 友好结构
- `SearchLiteGraphMessageEmitter`
  - 负责把消息推到 sink
  - 推送前统一经过 normalizer
- `SearchLiteGraphService`
  - 负责：
    - 编译后的图执行
    - 组装最终 state / route
    - 在兜底路径下读取 `GRAPH_MESSAGES`

这意味着：

- **service 不再直接关心 payload 递归规整的具体实现**
- **emitter 和 fallback path 也终于用上了同一套标准**

### 29.3 为什么这一步很值得做

这是一个典型的“把稳定性做成公共能力”的改造。

因为之前即使主路径已经优先直推 sink，
消息规范化却只在 fallback 回放路径里做得比较完整，
这会留下一个风险：

- 直推 sink 的消息
- 和 fallback 回放的消息
- 可能走不同的规范化规则

G8.6 之后，这个风险显著降低：

- **无论消息是直推还是回放，都经过同一个 normalizer**

### 29.4 这一步和 management 的关系

这一步虽然还不是 `management` 那种原生 `StreamingOutput`，
但它已经非常接近一个成熟 graph streaming 系统该有的形态：

- graph service 不再膨胀
- 输出细节不再散落在多个类里
- “消息如何安全流出”被收敛成一个独立能力

这会让后面继续往更 graph-native 的 streaming 演进时，代码基础更稳。

---

## 30. Step G8.7 完成内容（记录时间：2026-04-03）

本步骤目标：

- 继续把“消息如何流向 sink”从 adapter 中抽出来
- 让 adapter 更像“状态适配层”，而不是“半个 streaming 执行器”
- 进一步集中 graph 输出机制

本步骤已完成：

- 更新 `SearchLiteGraphMessageEmitter`
  - 新增：
    - `emitStream(threadId, Flux<SearchLiteMessage>)`
- 更新 `SearchLiteGraphStepOutputAdapter`
  - 当主路径有 live sink 时：
    - 不再自己写 `doOnNext(...).blockLast()`
    - 改为直接委托给：
      - `messageEmitter.emitStream(...)`

### 30.1 这一步为什么值得单独做

在 G8.6 之后，虽然 normalizer 已经抽出来了，
但 adapter 里仍然保留着一段很“底层”的 streaming 桥接逻辑：

- 订阅 `stepResult.messages()`
- 逐条发消息
- 等待流完成

这会带来一个结构问题：

- adapter 本来应该主要负责：
  - `SearchLiteStepResult -> graph state`
- 但实际上还夹带了一部分：
  - “怎样把 Flux 消息流送进 sink”

G8.7 做的事情，就是把这部分再往外推一步。

### 30.2 现在 adapter 和 emitter 的职责边界

到这一步，两者的职责分工更清楚了：

- `SearchLiteGraphStepOutputAdapter`
  - 负责：
    - 取出更新后的 `SearchLiteState`
    - 映射为 graph state
    - 决定走主路径还是兜底路径
- `SearchLiteGraphMessageEmitter`
  - 负责：
    - 单条消息发送
    - 批量消息发送
    - **消息流发送**
    - 发送前统一做 normalizer 规整

所以 G8.7 的本质是：

> **让 emitter 真正变成 graph 输出通道，而不是一个只会发单条消息的小工具。**

### 30.3 这一步和 management 的关系

这一步依然不是 `management` 的原生 `StreamingOutput`，
但它已经进一步逼近那种结构：

- 节点/适配层越来越少关心 sink 的发送细节
- 输出机制越来越集中
- 后面如果要继续替换成更 graph-native 的 streaming 实现，
  改动面会更小

---

## 31. Step G8.8 完成内容（记录时间：2026-04-03）

本步骤目标：

- 继续把“主路径直推 / 兜底缓冲”这类分支判断从 adapter 中抽出去
- 让 adapter 更专注于：
  - state 更新
  - graph state 映射
- 让 emitter 真正成为统一的消息分发入口

本步骤已完成：

- 更新 `SearchLiteGraphMessageEmitter`
  - 新增：
    - `dispatch(threadId, Flux<SearchLiteMessage>)`
    - `DispatchResult`
- 更新 `SearchLiteGraphStepOutputAdapter`
  - 不再自己判断：
    - 是否直接发 sink
    - 是否 `collectList()` 做兜底缓存
  - 现在统一委托给：
    - `messageEmitter.dispatch(...)`

### 31.1 这一步具体改变了什么

在 G8.7 之前，adapter 里虽然已经不再直接写 `doOnNext(...).blockLast()`，
但它仍然保留了“主路径 vs 兜底路径”的具体分支逻辑：

- 有 sink：
  - `emitStream(...)`
- 没有 sink：
  - `collectList().block()`
  - 再合并到 `GRAPH_MESSAGES`

G8.8 之后，这层判断被继续抽到了 emitter：

- `messageEmitter.dispatch(...)`
  - 统一决定：
    - 是直接发到 sink
    - 还是收集成 fallback 消息列表

adapter 只根据 `DispatchResult` 做后续 graph state 处理。

### 31.2 现在 adapter 的角色更像什么

到这一步，`SearchLiteGraphStepOutputAdapter` 更接近一个真正的：

- **step output -> graph state adapter**

它现在主要负责的是：

- 解析 `updatedState`
- 映射 graph state
- 根据 dispatch 结果决定：
  - 移除 `GRAPH_MESSAGES`
  - 或写入兜底消息

而不再亲自管理：

- Flux 消息流到底怎么发送
- sink 是否存在
- fallback 消息怎么收集

### 31.3 这一步和 management 的关系

`management` 的 graph 体系里，一个很重要的特点就是：

- **节点执行**
- **状态推进**
- **流式输出**

这几层职责分得比较开。

G8.8 虽然还是过渡式实现，
但它又把我们当前 lite backend 往这个方向推近了一步：

- emitter 成为统一消息分发口
- adapter 进一步瘦身
- 后面如果继续做更原生的 graph streaming，阻力会更小

---

## 32. Step G9.1 完成内容（记录时间：2026-04-04）

本步骤目标：

- 给 graph 主链路补上第二批条件分支里的第一条：
  - `SCHEMA_RECALL` 为空时不要继续进入 `ENHANCE -> SQL_GENERATE`
- 让“无有效 schema 命中”的场景尽早收口

本步骤已完成：

- 新增：
  - `SearchLiteSchemaRecallDispatcher`
- 更新：
  - `SearchLiteGraphConfiguration`
  - `SCHEMA_RECALL_NODE` 不再固定连到 `ENHANCE_NODE`
  - 改成条件边：
    - 有 `recalledTables` -> `ENHANCE_NODE`
    - 无 `recalledTables` -> `RESULT_NODE`
- 新增测试：
  - `SearchLiteSchemaRecallDispatcherTest`

### 32.1 这一步解决了什么问题

在 G9.1 之前，graph 主链路里这段是固定的：

- `SCHEMA_RECALL -> ENHANCE`

这意味着即使 schema recall 没有召回任何相关表，
系统也仍然会继续：

- 查询增强
- SQL 生成
- SQL 执行

这既浪费调用成本，也容易让系统在“缺乏结构依据”的情况下硬生成 SQL。

G9.1 把这条路径改成了真正的条件路由：

- **召回到表**：继续分析链路
- **没召回到表**：直接进入 `RESULT`

### 32.2 为什么这里先路由到 `RESULT` 而不是 `END`

这是一个有意识的设计选择。

如果直接 `END`：

- 用户只会看到前面阶段消息
- 没有一个统一的收尾结果

而进入 `RESULT` 的好处是：

- 仍然能保持当前 SSE 协议里的“结果收口”体验
- 后面我们还可以继续把：
  - “为什么没有继续执行 SQL”
  - “建议补充哪些实体/字段/时间范围”
  这种解释进一步做得更友好

所以当前 G9.1 选择的是：

- **无 schema 命中 -> `RESULT_NODE`**

而不是直接终止。

### 32.3 这一步和 management 的关系

这一步开始真正进入 `management` 风格 graph 的另一个核心能力：

- **不是只有 intent 才能分支**
- **中间节点也可以根据 state 决定是否继续推进**

这意味着我们现在的 graph 已经不只是“入口路由”，
而是开始具备：

- **过程中的条件裁剪能力**

这对后面继续做：

- `SQL_GENERATE` 空结果分支
- `SQL_EXECUTE` 失败分支

会形成一个很自然的模式复用。

---

## 33. Step G9.2 完成内容（记录时间：2026-04-04）

本步骤目标：

- 给 graph 主链路补上第二批条件分支里的第二条：
  - `SQL_GENERATE` 没有产出可执行 SQL 时，不再继续进入 `SQL_EXECUTE`
- 避免出现：
  - SQL 为空
  - 还继续执行数据库阶段
  - 最后再由结果阶段被动兜底

本步骤已完成：

- 新增：
  - `SearchLiteSqlGenerateDispatcher`
- 更新：
  - `SearchLiteGraphConfiguration`
  - `SQL_GENERATE_NODE` 不再固定连到 `SQL_EXECUTE_NODE`
  - 改成条件边：
    - 有可用 SQL -> `SQL_EXECUTE_NODE`
    - 无可用 SQL -> `RESULT_NODE`
- 新增测试：
  - `SearchLiteSqlGenerateDispatcherTest`

### 33.1 当前“可用 SQL”的判断规则

这一版先采用了一个比较克制、易解释的规则：

- SQL 非空
- 并且以：
  - `SELECT`
  - 或 `WITH`
  开头

这样做的好处是：

- 足够简单
- 和当前系统“只读查询”的约束一致
- 能覆盖：
  - 普通 `SELECT`
  - 带 CTE 的查询

### 33.2 为什么这一步有价值

在 G9.2 之前，graph 主链路里这段是固定的：

- `SQL_GENERATE -> SQL_EXECUTE`

所以一旦模型：

- 没输出任何 SQL
- 只输出了空字符串
- 或输出了明显无效的内容

系统仍然会继续尝试执行 SQL。

这会带来两个问题：

- 浪费执行阶段调用成本
- 错误位置被拖后，排障体验更差

G9.2 把这件事前移了：

- **SQL 生成阶段就决定“是否值得进入执行”**

### 33.3 这一步和 management 的关系

这一步继续强化了我们当前 graph 的一个重要方向：

- **中间阶段根据 state 做条件裁剪**

到现在为止，我们已经有了两类中途分支：

- `SCHEMA_RECALL` 无命中 -> `RESULT`
- `SQL_GENERATE` 无有效 SQL -> `RESULT`

这让 graph 逐步从“线性节点串联”演进成了更像 `management` 的：

- **状态驱动工作流**

---

## 34. Step G9.3 完成内容（记录时间：2026-04-04）

本步骤目标：

- 给 graph 主链路补上第二批条件分支里的第三条：
  - `SQL_EXECUTE` 之后根据执行结果做显式分支判断
- 即使当前成功/失败都先落到 `RESULT_NODE`，
  也要把“执行是否失败”这层语义独立出来

本步骤已完成：

- 新增：
  - `SearchLiteSqlExecuteDispatcher`
- 更新：
  - `SearchLiteGraphConfiguration`
  - `SQL_EXECUTE_NODE` 不再使用固定边
  - 改成条件边，由 dispatcher 根据 state 决定后续
- 新增测试：
  - `SearchLiteSqlExecuteDispatcherTest`

### 34.1 为什么这一步现在就值得做

从纯路由结果看，这一步目前还是：

- 执行成功 -> `RESULT_NODE`
- 执行失败 -> `RESULT_NODE`

看上去像“功能上没变”。

但这里真正重要的不是最终跳转目标，
而是：

- **graph 已经开始把“SQL 是否执行成功”显式建模成一个中间判断点**

这有两个好处：

- 当前：
  - 失败场景会更清楚地在 graph 里留下分支语义
- 后续：
  - 如果我们要引入：
    - `ERROR_RESULT_NODE`
    - 重试节点
    - fallback answer 节点
  - 就不需要再重改整段主链结构

### 34.2 当前 dispatcher 判断依据

当前这版 `SearchLiteSqlExecuteDispatcher` 的判断很直接：

- 如果 `error` 非空：
  - 视为执行失败
- 否则：
  - 视为执行成功

同时它会把：

- 错误信息
- 或结果行数

记到日志里，方便后续排查。

### 34.3 这一步和 management 的关系

这一步开始更明显地贴近 `management` 的另一个特点：

- **即使暂时走向同一个节点，也会把中间判断点单独抽出来**

因为在 graph/workflow 设计里，
“当前先共用一个收尾节点”和“没有分支能力”是两回事。

G9.3 完成后，我们当前 graph 主链已经具备了这三类中途条件裁剪能力：

- `SCHEMA_RECALL` 无命中
- `SQL_GENERATE` 无有效 SQL
- `SQL_EXECUTE` 执行结果判断

这为后面继续做更细粒度的：

- 错误分流
- 重试
- fallback

打下了比较好的结构基础。

## 35. 多轮上下文 V1（参考 management 的窗口式方案）

记录时间：2026-04-06

这一步开始，我们不再只把 `threadId` 当成 SSE/Graph 的运行标识，
而是让它真正承担“多轮对话上下文”的语义。

参考对象主要是 `management` 的：

- `MultiTurnContextManager`
- `GraphServiceImpl`

它的核心特点不是“做了一个很重的 memory 系统”，
而是：

- 按 `threadId` 维护最近几轮窗口
- 在每轮开始前构造 `multiTurnContext`
- 在每轮结束后回写当前轮摘要
- 对上下文长度做硬裁剪（默认只保留最近 5 轮）

我们这次基本沿着这条思路，做了一个适合 `search-lite` 的 V1。

### 35.1 新增了哪些核心对象

本次新增了：

- `ConversationTurn`
- `PendingConversationTurn`
- `PreparedConversationContext`
- `MultiTurnContextManager`

位置：

- `D:\\GitHub\\DataAgent\\data-agent-backend\\src\\main\\java\\com\\alibaba\\cloud\\ai\\dataagentbackend\\lite\\conversation`

职责拆分如下：

- `ConversationTurn`
  - 表示一个已经完成的历史轮次摘要
- `PendingConversationTurn`
  - 表示当前正在执行、尚未收口的一轮
- `PreparedConversationContext`
  - 表示新请求进入时，预先计算出的：
    - `multiTurnContext`
    - `contextualizedQuery`
- `MultiTurnContextManager`
  - 统一负责：
    - 最近几轮窗口维护
    - 当前轮 begin/finish/discard
    - `multiTurnContext` 构建
    - follow-up query 的上下文补全

### 35.2 为什么要同时引入 `multiTurnContext` 和 `contextualizedQuery`

这两个字段看起来有点像，但作用不同：

- `multiTurnContext`
  - 给 LLM prompt 用
  - 主要服务：
    - `INTENT`
    - `ENHANCE`
- `contextualizedQuery`
  - 给检索/召回链路用
  - 主要服务：
    - `EVIDENCE`
    - `SCHEMA_RECALL`
    - 以及后续 `SQL_GENERATE` 的 `effectiveQuery`

这是因为我们当前主链顺序是：

- `INTENT -> EVIDENCE -> SCHEMA -> SCHEMA_RECALL -> ENHANCE -> SQL_GENERATE`

如果只在 `ENHANCE` 阶段处理多轮问题，
那么前面的：

- evidence recall
- schema recall

仍然会只看到一句像“这些用户里谁下单最多”的追问，
召回质量会很不稳定。

所以这次我们增加了一个更早可用的：

- `contextualizedQuery`

它本质上是：

- 如果当前 query 明显依赖前文
- 就把上一轮的核心 query 补进当前 query

例如：

- 上一轮：`查询累计消费金额最高的用户`
- 当前轮：`这些用户里谁下单最多`

V1 会补成类似：

- `基于上一轮查询“查询累计消费金额最高的用户”，当前追问：这些用户里谁下单最多`

这样前面的 recall 阶段也能更早看到上下文。

### 35.3 这次在状态对象里新增了什么

`SearchLiteState` 新增了：

- `multiTurnContext`
- `contextualizedQuery`

并补了两个约定：

- `getRecallQuery()`
  - 优先返回 `contextualizedQuery`
  - 否则返回原始 `query`
- `getEffectiveQuery()`
  - 优先级改成：
    - `canonicalQuery`
    - `contextualizedQuery`
    - `query`

这意味着：

- recall 阶段优先用“补全后的追问”
- SQL 生成阶段优先用 canonical query；如果还没 canonical，再退回 contextualized query

### 35.4 这次把多轮上下文接到了哪些地方

#### 1）请求入口

在 `SearchLiteOrchestrator` 中，
每次请求进入时都会：

- `prepareTurn(threadId, query)`

得到：

- `multiTurnContext`
- `contextualizedQuery`

并写入 `SearchLiteState`。

这一步相当于 management 里：

- `buildContext(threadId)`
- `beginTurn(threadId, query)`

的组合版本。

#### 2）Intent

`IntentMinimaxStep` 现在会把：

- `Multi-turn context`

带进 prompt，
并显式告诉模型：

- 只有当前问题明显依赖前文时，才使用多轮上下文做分类判断

这样能更好地处理：

- “再看一下前10个”
- “改成最近30天”

这类单看当前句子并不完整的问题。

#### 3）Evidence Recall

`EvidenceFileStep` 这次没有直接引入一个更重的 LLM rewrite memory 机制，
而是先走了一版更轻的控制：

- evidence rewrite 不再只吃原始 `query`
- 改为优先吃：
  - `state.getRecallQuery()`

同时 SSE payload 中也额外输出了：

- `recallQuery`

方便我们观察多轮补全后的检索输入到底是什么。

#### 4）Schema Recall

`SchemaRecallStep` 也同步切到了：

- `state.getRecallQuery()`

这一步非常关键，
因为 schema recall 比 query enhance 更早执行。

#### 5）Enhance

`EnhanceMinimaxStep` 现在也会带上：

- `multiTurnContext`

并显式提示模型：

- 如果当前 query 是 follow-up，要用多轮上下文来补足省略条件和指代关系

### 35.5 这次如何控制上下文长度

这次延续了 management 的“窗口式”思路，
而不是一下子上复杂 memory：

- `search.lite.context.max-turn-history: 5`
- `search.lite.context.max-field-length: 240`

控制点包括：

- 最多只保留最近 5 轮
- 每个 turn 中的字段（query / canonical / sql / summary）都会做长度裁剪

也就是说：

- 我们优先解决“多轮追问能不能接得住”
- 不追求一开始就做长期记忆/向量化会话检索

### 35.6 这次如何回写当前轮

当前轮完成后会调用：

- `MultiTurnContextManager.finishTurn(state)`

回写内容包括：

- 用户原问题
- `contextualizedQuery`
- `canonicalQuery`
- `sql`
- `resultSummary`
- `intentClassification`

这里用了一个很重要的策略：

- 不是任何轮次都强制入历史
- 如果没有形成有效分析结果，就不会盲目污染 history

例如：

- 普通闲聊 `CHITCHAT`
  - 默认不会持久进多轮分析历史

### 35.7 这次和 management 的差异

虽然整体思路参考 management，
但我们这次也做了一个适合 lite 链路的补充：

- `management`
  - 更强调：
    - `multiTurnContext` 给 prompt 使用
- 我们
  - 除了 `multiTurnContext`
  - 还增加了：
    - `contextualizedQuery`

这是因为我们当前链路里：

- recall 阶段在 enhance 之前

如果不提前补全 query，
很多 follow-up query 会在 recall 阶段就掉精度。

所以这是一个“在 management 思路基础上，为 lite 主链做的顺序适配”。

### 35.8 当前 V1 的边界

这仍然只是多轮上下文 V1，
还没有做：

- 长期记忆
- 用户偏好 memory
- 向量化历史检索
- 多轮结果结构化实体抽取
- 基于错误恢复的 turn restart

但它已经足够支持第一批最常见的追问：

- 指代延续
- 条件补充
- 上一轮结果追问

也足够成为后面继续做：

- 多轮 NL2SQL
- 更强 evidence/schema recall
- 评测闭环

的基础。

## 36. Graph 收口：结果分流与 SQL 重试（记录时间：2026-04-06）

这一轮不是再加更多节点数量，
而是把当前 Graph 从“主链闭环”往“更像 workflow”推进一层。

改造目标主要有三个：

- 把 `RESULT` 之前的结果语义先整理清楚
- 给 `SQL_EXECUTE` 增加一次受控重试
- 让 graph 分支不再只是“都汇到 RESULT”，而是先经过一个显式的收口准备节点

### 36.1 为什么这一轮值得做

之前的主链虽然已经 graph 化，
但还存在几个典型问题：

- `SCHEMA_RECALL` 为空时，虽然能提前结束，但没有单独的结果语义
- `SQL_GENERATE` 为空时，也只是直接去 `RESULT`
- `SQL_EXECUTE` 失败后没有自动修正能力
- `RESULT` 节点需要同时处理：
  - 正常结果
  - 无 schema
  - 无 SQL
  - 执行失败

这说明之前的 graph 更像：

- “能分支”

但还不够像：

- “会根据失败类型决定怎么收口和怎么继续”

### 36.2 这次新增的 graph 语义字段

`SearchLiteState` / graph state 这次新增了：

- `sqlRetryCount`
- `lastFailedSql`
- `sqlRetryReason`
- `resultMode`

对应 graph key 也同步加到了：

- `SearchLiteGraphStateKeys`
- `SearchLiteGraphStateMapper`

这样做的意义是：

- SQL 重试不再只靠日志或瞬时异常
- 结果类型也不再只靠 `error != null` 这种弱判断

### 36.3 新增了两个中间节点

这次新增了：

- `SearchLiteSqlRetryGraphNode`
- `SearchLitePrepareResultGraphNode`

#### `SearchLiteSqlRetryGraphNode`

职责：

- 保存上一次失败的 SQL
- 保存失败原因
- `sqlRetryCount + 1`
- 清空 `error`
- 清空 `rows / resultSummary`
- 再回到 `SQL_GENERATE`

这一步的本质是：

- **把“执行失败后的再生成”显式建模成 graph 中的一个中间动作**

#### `SearchLitePrepareResultGraphNode`

职责：

- 在进入 `RESULT_NODE` 之前，先统一判断当前是哪种结果模式

当前会输出四类 `resultMode`：

- `success`
- `no_schema`
- `no_sql`
- `execution_error`

也就是说：

- 不是直接让 `RESULT` 自己猜“现在到底是为什么失败/为什么结束”
- 而是先由 graph 统一标好语义

### 36.4 SQL 执行失败后的重试策略

这次在 `SearchLiteSqlExecuteDispatcher` 里加了一版 V1 重试策略：

- 如果执行失败
- 且 `retryCount < maxAttempts`
- 且错误类型不是明显的连接/权限/超时类基础设施错误

那么：

- `SQL_EXECUTE -> SQL_RETRY -> SQL_GENERATE`

否则：

- `SQL_EXECUTE -> PREPARE_RESULT`

当前默认配置：

- `search.lite.graph.sql-retry.max-attempts: 1`

这版设计故意比较保守：

- 先做一次自动修正
- 避免把失败 query 带进无限重试

### 36.5 这次 graph 结构怎么变了

当前主链从：

- `... -> SQL_GENERATE -> SQL_EXECUTE -> RESULT`

变成了：

- `... -> SQL_GENERATE -> SQL_EXECUTE`
- `SQL_EXECUTE -> SQL_RETRY | PREPARE_RESULT`
- `SQL_RETRY -> SQL_GENERATE`
- `PREPARE_RESULT -> RESULT`

同时：

- `SCHEMA_RECALL` 无命中时
- `SQL_GENERATE` 无有效 SQL 时

也不再直接跳 `RESULT`，
而是先跳：

- `PREPARE_RESULT`

也就是说，
现在 graph 对“为什么结束”这件事有了更明确的中间语义层。

### 36.6 结果节点也随之变得更简单

`ResultMinimaxStep` / `ResultMockStep` 这次也一起收口了：

- 当 `resultMode` 已经明确时：
  - 直接走预定义结果总结
  - 不再强行请求 LLM 去总结一个“根本没查出来”的结果

例如：

- `no_schema`
  - 直接给用户明确说明“当前没有召回到相关数据表”
- `no_sql`
  - 直接提示“当前问题未生成可执行 SQL”
- `execution_error`
  - 直接输出执行失败原因

这让 `RESULT` 节点更像：

- “负责表达”

而不是：

- “既负责判因，又负责表达”

### 36.7 这一步和 management 的关系

这次继续贴近了 management 的两个思路：

- **失败场景要显式建模**
- **即使最后都落到一个节点，中间也要有清晰的 workflow 语义**

虽然我们现在还没有做到它那种更完整的：

- 多次 SQL retry
- 更细的 fallback graph
- human feedback 后 restart

但这次已经把最关键的骨架补出来了：

- retry
- prepare-result
- result-mode

### 36.8 当前仍然保留的边界

这一轮做完后，Graph 仍然不是最终形态，主要还剩这些边界：

- `RESULT` 还没有真正拆成多个 node
- retry 目前只有一轮
- 重试判断规则还偏规则化，而不是结合错误分类器/LLM 修复
- adapter / step bridge 痕迹还在

但从工程价值上看，
这一轮已经把 Graph 从：

- “主链闭环”

推进到了：

- “具备失败恢复和结果语义收口能力的 workflow”
