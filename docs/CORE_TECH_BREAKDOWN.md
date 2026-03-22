# DataAgent 核心技术拆解指南（按物理结构，屏蔽外围工程噪声）

> 本文只聚焦 **Agent 的运行机制**：控制流/上下文与记忆/Prompt 组装/LLM 调用/工具（SQL、Python、MCP）路由与执行/状态更新与输出流；刻意忽略 UI 渲染、常规错误捕获、复杂日志、鉴权等边缘工程逻辑。

---

## 模块一：核心控制流（Main Loop）的物理追踪

### 1) 项目运行入口点（Entry Points）

1. **Spring Boot 启动入口**
   - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/DataAgentApplication.java`
   - 关键：`DataAgentApplication.main(String[] args)` → `SpringApplication.run(...)`

2. **典型 Agent 任务入口（HTTP 流式）**
   - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/controller/GraphController.java`
   - 关键：`GraphController.streamSearch(...)`（SSE）→ `GraphService.graphStreamProcess(...)`

3. **工具化入口（MCP Tool）**
   - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/mcp/McpServerService.java`
   - 关键：`McpServerService.nl2SqlToolCallback(...)` → `GraphService.nl2sql(...)`
   - MCP Tool 暴露：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/McpServerConfig.java`（`@ToolCallbackProvider`）

---

### 2) 一个典型任务的完整生命周期（以 `/api/stream/search` 为主线）

> 你可以把它理解为：**HTTP/SSE 只是“输入输出壳”**，真正的 Main Loop 是 `CompiledGraph.stream(...)` 驱动的 **StateGraph 工作流**。

#### Step 0：接收输入 → 请求对象构造（Transport 层，尽量忽略）
- 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/controller/GraphController.java`
- 动作：
  - `GraphController.streamSearch(...)`：从 queryString 取 `agentId/threadId/query/humanFeedback...`
  - 构造 `GraphRequest`：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/dto/GraphRequest.java`
  - 调用：`graphService.graphStreamProcess(sink, request)`

#### Step 1：线程上下文初始化（threadId / 流上下文 / 记忆注入）
- 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/GraphServiceImpl.java`
- 关键方法：
  - `graphStreamProcess(...)`：确保 `threadId`，创建/复用 `StreamContext`
  - `handleNewProcess(GraphRequest)`：构造初始 state，并启动图流
- 状态/记忆相关对象：
  - `StreamContext`：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/Context/StreamContext.java`
  - 多轮上下文管理：`MultiTurnContextManager`：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/Context/MultiTurnContextManager.java`
- 关键动作（核心）：
  - `multiTurnContextManager.buildContext(threadId)`：把历史 turn 压成可注入 Prompt 的字符串
  - `multiTurnContextManager.beginTurn(threadId, query)`：开始记录本轮 planner 输出（用于后续写回记忆）
  - `compiledGraph.stream(initialState, RunnableConfig.builder().threadId(threadId).build())`
- 初始 state（关键键）来自：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/constant/Constant.java`
  - `INPUT_KEY`、`AGENT_ID`、`MULTI_TURN_CONTEXT`、`IS_ONLY_NL2SQL`、`HUMAN_REVIEW_ENABLED`、`TRACE_THREAD_ID`

#### Step 2：Main Loop 的“调度器”装配与编译（工作流定义）
- 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java`
- 关键方法：`DataAgentConfiguration.nl2sqlGraph(...)`
- 核心动作：
  - `new StateGraph(NL2SQL_GRAPH_NAME, keyStrategyFactory)`
  - `.addNode(nodeKey, nodeBeanUtil.getNodeBeanAsync(XxxNode.class))`
  - `.addEdge(...) / .addConditionalEdges(..., dispatcher, routeMap)`
  - 产物：`StateGraph` → 在 `GraphServiceImpl` 构造器里 `stateGraph.compile(...)` 得到 `CompiledGraph`
- 编译发生处：
  - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/GraphServiceImpl.java`
  - `GraphServiceImpl(...)`：`stateGraph.compile(CompileConfig.builder().interruptBefore(HUMAN_FEEDBACK_NODE).build())`

#### Step 3：节点执行（NodeAction.apply）与边路由（EdgeAction.apply）
> 每个节点都是一个 **纯函数风格的状态变换器**：输入是 `OverAllState`，输出是 `Map<String,Object>`（写回 state）；路由由 Dispatcher 决定下一跳。

1. **意图识别（IntentRecognition）**
   - 节点文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/IntentRecognitionNode.java`
   - 方法：`IntentRecognitionNode.apply(OverAllState)`
   - Prompt 组装：`PromptHelper.buildIntentRecognitionPrompt(...)`
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/prompt/PromptHelper.java`
   - LLM 调用：`LlmService.callUser(prompt)`
     - 接口：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/llm/LlmService.java`
   - 输出写回：`INTENT_RECOGNITION_NODE_OUTPUT`
   - 路由 Dispatcher：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/dispatcher/IntentRecognitionDispatcher.java`
     - 方法：`IntentRecognitionDispatcher.apply(OverAllState)` → `EVIDENCE_RECALL_NODE` 或 `END`

2. **证据召回（EvidenceRecall，RAG-ish）**
   - 节点文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/EvidenceRecallNode.java`
   - 方法：`EvidenceRecallNode.apply(OverAllState)`
   - 两段核心动作：
     - Query Rewrite Prompt：`PromptHelper.buildEvidenceQueryRewritePrompt(...)` → `LlmService.callUser(...)`
     - 向量召回：`AgentVectorStoreService.getDocumentsForAgent(agentId, query, vectorType)`
       - 接口：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/vectorstore/AgentVectorStoreService.java`
       - 实现：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/vectorstore/AgentVectorStoreServiceImpl.java`
   - 召回过滤（把“DB 里被启用的知识/术语”映射到向量库 filter）：
     - `DynamicFilterService.buildDynamicFilter(...)`
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/vectorstore/DynamicFilterService.java`
   - 输出写回：`EVIDENCE`（被后续 QueryEnhance/Planner/NL2SQL 使用）

3. **问题增强（QueryEnhance）**
   - 节点文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/QueryEnhanceNode.java`
   - 方法：`QueryEnhanceNode.apply(OverAllState)`
   - Prompt 组装：`PromptHelper.buildQueryEnhancePrompt(multiTurn, latestQuery, evidence)`
   - LLM 调用：`LlmService.callUser(prompt)`
   - 输出解析：`JsonParseUtil.tryConvertToObject(...)`（把 LLM JSON 转为 `QueryEnhanceOutputDTO`）
   - 输出写回：`QUERY_ENHANCE_NODE_OUTPUT`（后续用它的 `canonicalQuery` 贯穿全流程）

4. **Schema 召回（SchemaRecall）**
   - 节点文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/SchemaRecallNode.java`
   - 方法：`SchemaRecallNode.apply(OverAllState)`
   - 数据源选择：`AgentDatasourceMapper.selectActiveDatasourceIdByAgentId(...)`（MyBatis）
   - 表/列召回：`SchemaService.getTableDocumentsByDatasource(...)`、`getColumnDocumentsByTableName(...)`
   - 输出写回：
     - `TABLE_DOCUMENTS_FOR_SCHEMA_OUTPUT`
     - `COLUMN_DOCUMENTS__FOR_SCHEMA_OUTPUT`

5. **表关系推断 + 语义模型拼装（TableRelation）**
   - 节点文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/TableRelationNode.java`
   - 方法：`TableRelationNode.apply(OverAllState)`
   - 关键动作（抽象视角）：
     - 从召回的表/列 documents 还原 `SchemaDTO`
     - 结合逻辑外键（`DatasourceService.getLogicalRelations(...)`）补全 JOIN/关系
     - 结合 `SemanticModelService` 生成/注入语义模型 Prompt（写入 `GENEGRATED_SEMANTIC_MODEL_PROMPT`）
     - 读取 DB 配置与方言：`DatabaseUtil.getAgentDbConfig(...)` / `DB_DIALECT_TYPE`
   - 输出写回：`TABLE_RELATION_OUTPUT`（后续 NL2SQL 生成与一致性校验依赖它）

6. **可行性评估（FeasibilityAssessment）**
   - 节点文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/FeasibilityAssessmentNode.java`
   - 方法：`FeasibilityAssessmentNode.apply(OverAllState)`
   - Prompt：`PromptHelper.buildFeasibilityAssessmentPrompt(canonicalQuery, schema, evidence, multiTurn)`
   - 输出写回：`FEASIBILITY_ASSESSMENT_NODE_OUTPUT`
   - 路由 Dispatcher：`FeasibilityAssessmentDispatcher`（在 `DataAgentConfiguration` 的 conditionalEdges 里挂载）

7. **Planner：生成“执行计划”（把 tool routing 显式化）**
   - 节点文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/PlannerNode.java`
   - 方法：`PlannerNode.apply(OverAllState)`
   - Prompt 模板：`PromptConstant.getPlannerPromptTemplate()` → `resources/prompts/planner.txt`
     - Prompt 加载：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/prompt/PromptLoader.java`
   - 关键设计点：
     - 用 `BeanOutputConverter<Plan>` 生成 `format` 约束，让 LLM 按 `Plan` JSON 输出
     - 计划 JSON 作为字符串写回 state：`PLANNER_NODE_OUTPUT`

8. **PlanExecutor：验证计划 + 决定下一跳（工具/函数路由解析）**
   - 节点文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/PlanExecutorNode.java`
   - 方法：`PlanExecutorNode.apply(OverAllState)`
   - 计划解析：`PlanProcessUtil.getPlan(state)` / `getCurrentStepNumber(state)`
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/util/PlanProcessUtil.java`
   - 关键写回：
     - `PLAN_VALIDATION_STATUS`、`PLAN_VALIDATION_ERROR`、`PLAN_REPAIR_COUNT`
     - `PLAN_NEXT_NODE`（值是 `SQL_GENERATE_NODE` / `PYTHON_GENERATE_NODE` / `REPORT_GENERATOR_NODE` / `HUMAN_FEEDBACK_NODE`）
   - 路由 Dispatcher：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/dispatcher/PlanExecutorDispatcher.java`
     - 方法：`PlanExecutorDispatcher.apply(OverAllState)`（失败回 `PLANNER_NODE` 修复；成功转 `PLAN_NEXT_NODE`）

9. **SQL 工具链：生成 →（语义一致性校验）→ 执行 → 结果写回**
   - SQL 生成节点：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/SqlGenerateNode.java`
     - 方法：`SqlGenerateNode.apply(OverAllState)`
     - 调用：`Nl2SqlService.generateSql(SqlGenerationDTO)`（内部走 LLM Prompt）
       - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/nl2sql/Nl2SqlServiceImpl.java`
     - 写回：`SQL_GENERATE_OUTPUT`、`SQL_GENERATE_COUNT`、`SQL_REGENERATE_REASON`
   - 语义一致性节点：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/SemanticConsistencyNode.java`
     - 方法：`SemanticConsistencyNode.apply(OverAllState)` → `Nl2SqlService.performSemanticConsistency(...)`
     - 写回：`SEMANTIC_CONSISTENCY_NODE_OUTPUT` 或 `SQL_REGENERATE_REASON=semantic(...)`
   - SQL 执行节点：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/SqlExecuteNode.java`
     - 方法：`SqlExecuteNode.apply(OverAllState)`（读取 `SQL_GENERATE_OUTPUT` → 执行 → 聚合 step 结果）
     - 结果写回：
       - `SQL_EXECUTE_NODE_OUTPUT`（`step_n -> json`）
       - `SQL_RESULT_LIST_MEMORY`（给 Python 工具链作为输入样本/全量输入）
   - 路由 Dispatcher：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/dispatcher/SQLExecutorDispatcher.java`
     - 逻辑：执行失败→回 `SQL_GENERATE_NODE`；成功→回 `PLAN_EXECUTOR_NODE`

10. **Python 工具链：生成 → 容器执行 → 分析总结 → 写回到 step 结果**
   - Python 生成节点：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/PythonGenerateNode.java`
     - 方法：`PythonGenerateNode.apply(OverAllState)`
     - Prompt 模板：`resources/prompts/python-generator.txt`（通过 `PromptConstant`/`PromptLoader`）
     - 写回：`PYTHON_GENERATE_NODE_OUTPUT`
   - Python 执行节点：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/PythonExecuteNode.java`
     - 方法：`PythonExecuteNode.apply(OverAllState)`
     - 工具执行入口：`CodePoolExecutorService.runTask(TaskRequest)`
       - 接口：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/code/CodePoolExecutorService.java`
       - Docker 实现（容器池）：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/code/impls/DockerCodePoolExecutorService.java`
     - 写回：`PYTHON_EXECUTE_NODE_OUTPUT`、`PYTHON_IS_SUCCESS`、`PYTHON_TRIES_COUNT`、`PYTHON_FALLBACK_MODE`
   - Python 分析节点（把 python 输出转成自然语言洞察，回填到 step_n_analysis）：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/PythonAnalyzeNode.java`
     - 方法：`PythonAnalyzeNode.apply(OverAllState)`
     - 写回：更新 `SQL_EXECUTE_NODE_OUTPUT["step_n_analysis"]`，并 `PLAN_CURRENT_STEP + 1`

11. **最终输出：报告生成（ReportGenerator）**
   - 节点文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/ReportGeneratorNode.java`
   - 方法：`ReportGeneratorNode.apply(OverAllState)`
   - Prompt：`PromptHelper.buildReportGeneratorPromptWithOptimization(...)`
   - LLM 调用：`LlmService.callUser(...)`
   - 输出写回：`RESULT`（并清理部分中间 state，如 `PLANNER_NODE_OUTPUT`/`SQL_EXECUTE_NODE_OUTPUT` 等）

12. **人类反馈（Human-in-the-loop）：中断 → 更新 state → 恢复运行**
   - Graph 编译配置：`GraphServiceImpl` 在 compile 时 `interruptBefore(HUMAN_FEEDBACK_NODE)`
   - 反馈输入入口：
     - `GraphServiceImpl.handleHumanFeedback(GraphRequest)`
     - 关键：`compiledGraph.updateState(baseConfig, stateUpdate)` → `compiledGraph.stream(null, resumeConfig)`
   - 反馈节点：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/node/HumanFeedbackNode.java`
     - 方法：`HumanFeedbackNode.apply(OverAllState)`（读取 `HUMAN_FEEDBACK_DATA`，产出下一跳）
   - 反馈路由：
     - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/workflow/dispatcher/HumanFeedbackDispatcher.java`

#### Step 4：LLM 调用的物理落点（ChatClient/Model）
- 统一抽象：`LlmService`
  - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/llm/LlmService.java`
  - 实现：`StreamLlmService` / `BlockLlmService`（分别走 `ChatClient.stream()` 与 `ChatClient.call()`）
    - `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/llm/impls/StreamLlmService.java`
    - `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/llm/impls/BlockLlmService.java`
- ChatClient 构建与热切换：
  - `AiModelRegistry.getChatClient()`：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/aimodelconfig/AiModelRegistry.java`
  - 动态 Model 工厂（把多厂商统一成 OpenAI 协议风格，靠 baseUrl/paths 兼容）：
    - `DynamicModelFactory.createChatModel(...)`：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/aimodelconfig/DynamicModelFactory.java`

#### Step 5：输出返回（Streaming）
- 输出分发：
  - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/GraphServiceImpl.java`
  - 关键：`subscribeToFlux(...)` → `handleNodeOutput(...)` → `handleStreamNodeOutput(...)`
  - 每个 chunk 被包装为：
    - `StreamingOutput`（图内部事件，含 `node()` 与 `chunk()`）
    - `GraphNodeResponse`（SSE 对前端的输出 DTO）
      - `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/vo/GraphNodeResponse.java`
- Streaming 输出生成器的“关键胶水”：
  - 文件：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/util/FluxUtil.java`
  - 关键：`createStreamingGeneratorWithMessages(...)`（收集 LLM 输出 + 映射为 state 更新 + 变成 StreamingOutput）
- 记忆写回：
  - `GraphServiceImpl.handleStreamNodeOutput(...)`：当 `node == PlannerNode` 时 `multiTurnContextManager.appendPlannerChunk(...)`
  - `GraphServiceImpl.handleStreamComplete(...)`：`multiTurnContextManager.finishTurn(threadId)`

---

## 模块二：最小可行性（MVP）骨架提取

> 目标：**只保留能跑通“接收输入 → 上下文/记忆 → Prompt → LLM → 路由 → 工具执行 → 状态更新 → 输出”** 的骨架；其余（UI、会话持久化、文件上传、复杂日志/观测、各种 DB 适配细节）可剥离或用 stub 替换。

下面给出基于当前物理结构的 **MVP 精简文件树（按“必须保留/建议保留”划分）**：

```text
pom.xml
data-agent-management/
  pom.xml
  src/main/java/com/alibaba/cloud/ai/dataagent/
    DataAgentApplication.java                         # 启动入口
    constant/Constant.java                            # State keys / Node keys
    config/
      DataAgentConfiguration.java                      # StateGraph 装配 + VectorStore/ToolResolver/Embedding 代理
      McpServerConfig.java                             # (可选) MCP Tool 暴露
    dto/
      GraphRequest.java                                # 运行时输入
      planner/                                         # Plan / ExecutionStep 等（工具路由协议）
      prompt/                                          # LLM 输出结构体（intent/query enhance/sql...）
      schema/                                          # SchemaDTO/ColumnDTO/TableDTO（NL2SQL 的结构载体）
    prompt/
      PromptLoader.java                                # 从 resources/prompts 加载模板
      PromptConstant.java                              # PromptTemplate 入口
      PromptHelper.java                                # 组装 Prompt 的纯函数集合
    service/
      graph/
        GraphService.java
        GraphServiceImpl.java                          # compiledGraph.stream 主循环 + SSE 输出
        Context/
          StreamContext.java
          MultiTurnContextManager.java                 # 多轮记忆（轻量 in-memory）
      llm/
        LlmService.java
        impls/StreamLlmService.java                    # ChatClient.stream()
        impls/BlockLlmService.java                     # ChatClient.call()
      aimodelconfig/
        AiModelRegistry.java                           # ChatClient/EmbeddingModel 缓存与刷新
        DynamicModelFactory.java                        # 创建 ChatModel/EmbeddingModel（baseUrl 多厂商兼容）
        ModelConfigDataService.java (+实现/DTO/Mapper)  # 读取当前激活模型配置（可被 stub 替代）
      vectorstore/                                     # (建议保留) EvidenceRecall 的最小召回能力
        AgentVectorStoreService.java
        AgentVectorStoreServiceImpl.java
        SimpleVectorStoreInitialization.java            # 本地持久化（SimpleVectorStore）
        DynamicFilterService.java                       # “DB 启用状态”→“向量 filter”
      nl2sql/                                           # (建议保留) SQL 生成/一致性校验 Prompt + LLM 调用
        Nl2SqlService.java
        Nl2SqlServiceImpl.java
      code/                                             # (可选) Python 工具执行（容器/本地）
        CodePoolExecutorService.java
        impls/...
    util/
      FluxUtil.java                                    # Streaming generator 胶水
      StateUtil.java                                   # state 取值/反序列化
      PlanProcessUtil.java                              # Plan JSON → ExecutionStep
      ChatResponseUtil.java                             # ChatResponse → text
      JsonParseUtil.java / JsonUtil.java / MarkdownParserUtil.java
    workflow/
      node/                                             # 节点=动作（LLM/检索/执行/汇总）
      dispatcher/                                       # 边路由（下一跳选择）

  src/main/resources/
    application.yml                                     # 最小运行配置（模型/向量库/执行器等）
    prompts/*.txt                                       # 所有 Prompt 模板
```

> 说明：如果你希望 MVP **真的能编译运行** 而不是“概念骨架”，`SchemaService/DatabaseUtil/MyBatis mapper` 这类依赖要么整体保留，要么用 stub 替换（否则 `SchemaRecallNode/SqlExecuteNode/TableRelationNode` 会缺 Bean）。

---

## 模块三：关键技术栈的场景化映射（从依赖 → 回到代码）

> 只挑“决定 Agent 运行机制”的依赖；常规基础库（Spring 基础、Lombok、commons-* 等）不展开。

### A) 核心调度与路由层

1. **spring-ai-alibaba-graph-core（StateGraph / CompiledGraph / NodeAction / EdgeAction）**
   - 依赖：`data-agent-management/pom.xml` → `com.alibaba.cloud.ai:spring-ai-alibaba-graph-core`
   - 代码落点：
     - 工作流装配：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java`（`nl2sqlGraph(...)`）
     - 运行主循环：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/GraphServiceImpl.java`（`compiledGraph.stream(...)`/`updateState(...)`）
     - 节点接口：所有 `workflow/node/*Node.java` 实现 `NodeAction.apply(OverAllState)`
     - 路由接口：所有 `workflow/dispatcher/*Dispatcher.java` 实现 `EdgeAction.apply(OverAllState)`
   - 解决的问题（一句话）：把“Agent 运行时”抽象成 **可编译、可中断、可恢复的状态机工作流**，用显式 state key 管理跨节点数据流与重试/分支。

2. **Reactor + Spring WebFlux（Flux/Sinks/SSE）**
   - 依赖：`data-agent-management/pom.xml` → `spring-boot-starter-webflux`
   - 代码落点：
     - SSE 入口：`GraphController.streamSearch(...)`
     - 流式订阅与回传：`GraphServiceImpl.subscribeToFlux(...)`、`StreamContext`
   - 解决的问题（一句话）：把图执行的 `Flux<NodeOutput>` **实时转成 SSE chunk**，实现“边推理边展示”的用户体验。

### B) 记忆与检索层（向量存储等）

1. **多轮记忆（轻量 in-memory turn history）**
   - 代码落点：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/Context/MultiTurnContextManager.java`
   - 解决的问题（一句话）：在不引入复杂对话存储的情况下，把“用户问题 + Planner 输出”压缩为可注入 Prompt 的历史上下文（`MULTI_TURN_CONTEXT`）。

2. **Spring AI VectorStore（SimpleVectorStore / ElasticsearchVectorStore）**
   - 依赖：
     - 默认：`SimpleVectorStore`（通过 `DataAgentConfiguration.simpleVectorStore(...)` 兜底）
     - 可选：`spring-ai-starter-vector-store-elasticsearch`
   - 代码落点：
     - VectorStore Bean：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java`
     - 召回服务：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/vectorstore/AgentVectorStoreServiceImpl.java`
   - 解决的问题（一句话）：为 EvidenceRecall 提供 **相似度检索**（并可在 ES 模式下扩展关键字检索与融合）。

3. **Hybrid Retrieval（向量 + 关键词 + 融合）**
   - 依赖：`spring-ai-starter-vector-store-elasticsearch` + `co.elastic.clients:elasticsearch-java`
   - 代码落点：
     - 策略工厂：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/hybrid/factory/HybridRetrievalStrategyFactory.java`
     - ES 混合召回：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/hybrid/retrieval/impl/ElasticsearchHybridRetrievalStrategy.java`
     - 融合策略（RRF）：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/hybrid/fusion/impl/RrfFusionStrategy.java`
   - 解决的问题（一句话）：当“纯向量相似度”不足以覆盖业务术语/精确关键词时，用 **关键词检索 + 融合排序** 提升证据召回稳健性。

### C) 工具与执行层

1. **Spring AI ChatClient / ChatModel / EmbeddingModel（统一 LLM 访问层）**
   - 依赖：`spring-ai` BOM（父 `pom.xml`）+（可选）`spring-ai-alibaba-dashscope`
   - 代码落点：
     - 统一 LLM 抽象：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/llm/LlmService.java`
     - ChatClient 缓存：`AiModelRegistry.getChatClient()`（`service/aimodelconfig/AiModelRegistry.java`）
     - 动态模型工厂：`DynamicModelFactory.createChatModel(...)`（`service/aimodelconfig/DynamicModelFactory.java`）
   - 解决的问题（一句话）：把不同供应商/不同协议差异，收敛到 `LlmService.call*()`，让工作流节点只关心 Prompt 与结构化输出。

2. **MCP Server（把 DataAgent 能力暴露为可调用工具）**
   - 依赖：`data-agent-management/pom.xml` → `org.springframework.ai:spring-ai-starter-mcp-server-webflux`
   - 代码落点：
     - Tool 实现：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/mcp/McpServerService.java`（`@Tool`）
     - Tool 注册：`data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/McpServerConfig.java`
     - Tool Resolver 聚合（避免循环依赖）：`DataAgentConfiguration.toolCallbackResolver(...)`
   - 解决的问题（一句话）：让外部（或上层 Agent/IDE）能用 **标准化 tool 协议** 调用“列 Agent / NL2SQL”等能力，而不必绑死在 HTTP Controller 形态上。

3. **Python 代码执行（Docker 容器池）**
   - 依赖：`data-agent-management/pom.xml` → `com.github.docker-java:*`
   - 代码落点：
     - 工具执行入口：`PythonExecuteNode.apply(...)` → `CodePoolExecutorService.runTask(...)`
     - Docker 容器池实现：`service/code/impls/DockerCodePoolExecutorService.java`（底层 `docker-java`）
   - 解决的问题（一句话）：把“LLM 生成的 Python”放到受控环境里执行（资源/超时/隔离），并把结果写回工作流 state 供报告生成使用。

---

## 模块四：基于组件的数据流向代码阅读路线（从核心枢纽向外围扩展）

> 目标：顺着“数据在 state 里怎么流转”来读代码，而不是按目录线性扫。

1. **从总入口建立全局心智模型**
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/DataAgentApplication.java` 的 `main(...)`，确认这是一个 Spring Boot 应用。

2. **先把“状态机工作流”读透（这是 Main Loop 本体）**
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/config/DataAgentConfiguration.java` 的 `nl2sqlGraph(...)`：
     - 关注 `.addNode(...)` 列表（有哪些节点）
     - 关注 `.addConditionalEdges(..., Dispatcher, routeMap)`（分支/重试/回路）
     - 关注 `KeyStrategyFactory`（state key 的合并策略：REPLACE/APPEND 等）

3. **再读“运行时如何驱动这张图”**
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/GraphServiceImpl.java`：
     - `handleNewProcess(...)`：初始 state 注入哪些键（`MULTI_TURN_CONTEXT`、`HUMAN_REVIEW_ENABLED` 等）
     - `compiledGraph.stream(...)` 的入参（`RunnableConfig.threadId` 如何把一次运行和线程绑定）
     - `handleStreamNodeOutput(...)`：如何把 `StreamingOutput(node, chunk)` 变成 SSE，并顺便收集 planner chunk 写入记忆

4. **掌握 state keys（否则后面会“看不见数据”）**
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/constant/Constant.java`：
     - 把“节点 key”和“输出 key”对齐（例如 `PLANNER_NODE_OUTPUT`、`SQL_GENERATE_OUTPUT`、`SQL_EXECUTE_NODE_OUTPUT`）

5. **理解“多轮记忆”在物理上如何注入与回写**
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/graph/Context/MultiTurnContextManager.java`：
     - `buildContext(...)` 如何格式化历史
     - `beginTurn/appendPlannerChunk/finishTurn` 如何把 planner 输出写入历史
   - 回到 `GraphServiceImpl.handleNewProcess(...)` 与 `handleStreamComplete(...)` 看它何时被调用。

6. **看清 LLM 调用栈（节点只写 Prompt，但最终落到哪里）**
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/llm/LlmService.java`
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/llm/impls/StreamLlmService.java`
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/aimodelconfig/AiModelRegistry.java`：
     - `getChatClient()` 何时初始化/缓存/刷新
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/service/aimodelconfig/DynamicModelFactory.java`：
     - 如何把不同 provider 统一为 `OpenAiChatModel`（baseUrl/paths/proxy）

7. **再回到“Prompt 是怎么被组装出来的”**
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/prompt/PromptLoader.java`
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/prompt/PromptConstant.java`
   - 阅读 `data-agent-management/src/main/java/com/alibaba/cloud/ai/dataagent/prompt/PromptHelper.java`
   - 对照模板文件：`data-agent-management/src/main/resources/prompts/*.txt`

8. **沿着数据流逐节点阅读（从“最前置”到“最靠近工具执行”）**
   - 读 `workflow/node/IntentRecognitionNode.java` + `workflow/dispatcher/IntentRecognitionDispatcher.java`：理解“先分流、后进入重流程”的门控。
   - 读 `workflow/node/EvidenceRecallNode.java`：
     - 再读 `service/vectorstore/AgentVectorStoreServiceImpl.java` 与 `DynamicFilterService.java`：理解“DB 启用状态→向量检索过滤”的桥接。
   - 读 `workflow/node/QueryEnhanceNode.java`：理解 canonicalQuery 如何成为后续主语。
   - 读 `workflow/node/SchemaRecallNode.java`、`workflow/node/TableRelationNode.java`：理解 SchemaDTO 如何被拼装为 NL2SQL 可用的结构 prompt。
   - 读 `workflow/node/FeasibilityAssessmentNode.java`：理解为什么需要在 Planner 前做“可行性闸门”。

9. **读“计划即路由”的关键实现**
   - 读 `workflow/node/PlannerNode.java`：理解 Plan JSON 输出格式如何被约束（`BeanOutputConverter` + prompt format）
   - 读 `util/PlanProcessUtil.java`：理解 plan JSON 解析与 step 索引
   - 读 `workflow/node/PlanExecutorNode.java` + `workflow/dispatcher/PlanExecutorDispatcher.java`：理解“验证失败回退修复”的闭环

10. **读工具执行链（SQL → Python → Report）**
   - 读 `workflow/node/SqlGenerateNode.java` → 再读 `service/nl2sql/Nl2SqlServiceImpl.java`：理解 SQL 生成/修复 prompt 的选择分支。
   - 读 `workflow/node/SemanticConsistencyNode.java`：理解一致性校验如何影响回路（触发 `SQL_REGENERATE_REASON`）。
   - 读 `workflow/node/SqlExecuteNode.java`：理解执行结果如何写入 `SQL_EXECUTE_NODE_OUTPUT` 与 `SQL_RESULT_LIST_MEMORY`。
   - 读 `workflow/node/PythonGenerateNode.java`、`PythonExecuteNode.java`、`PythonAnalyzeNode.java`：
     - 再读 `service/code/CodePoolExecutorService.java` 与 `service/code/impls/*`：理解“受控执行环境”与重试/降级策略。
   - 读 `workflow/node/ReportGeneratorNode.java`：理解最终报告 prompt 如何拼装（把 executionResults 展开为叙述）。

11. **最后再看“人类反馈”如何中断与恢复图执行**
   - 读 `GraphServiceImpl.handleHumanFeedback(...)`：理解 `compiledGraph.updateState(...)` + `stream(resumeConfig)` 的恢复机制
   - 读 `workflow/node/HumanFeedbackNode.java` + `workflow/dispatcher/HumanFeedbackDispatcher.java`

12. **（可选扩展）把能力暴露为 MCP Tools**
   - 读 `service/mcp/McpServerService.java`（`@Tool` 方法签名就是 tool schema）
   - 读 `config/McpServerConfig.java` 与 `config/DataAgentConfiguration.toolCallbackResolver(...)`（理解如何避开循环依赖并聚合 tools）

