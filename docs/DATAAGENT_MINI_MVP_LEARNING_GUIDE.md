# DataAgent → DataAgent-mini 学习路线与MVP构建指南

> 目标：在 `D:\GitHub\DataAgent-mini` 中实现一个可运行的最小版本（MVP），用于系统性学习 `D:\GitHub\DataAgent` 的技术栈与核心设计。  
> 本文件由对当前仓库代码结构的“逆向阅读路线”组织而成（编写日期：2026-03-18）。

---

## 0. 你最终要做出的 MVP（建议定义）

**MVP 的“可执行”定义（端到端闭环）：**

1. 提供一个 HTTP 接口（建议先非流式，再做 SSE 流式）  
2. 输入：自然语言问题（query）+ 选择的 agentId（或默认 agent）  
3. 输出：生成的 SQL（+ 可选：SQL 执行结果）  
4. 数据库：内置 H2 内存库（复用项目已有的 `application-h2.yml` 思路与初始化脚本）  
5. LLM：优先支持 OpenAI 兼容接口（项目强调“OpenAI API 规范兼容”）；也允许先做 **FakeLLM**（固定返回或基于规则的返回）以便先跑通架构

**MVP 不做/后置（第一阶段刻意裁剪）：**

- 前端完整 UI（可以先用 `curl`/Postman 验证，后续再接 Vue3）  
- 知识库上传/embedding 入库/向量检索增强（RAG）  
- Python 代码生成与执行（code executor）  
- Human-in-the-loop 审核流  
- MCP server 对接（可作为后续增量）

---

## 1. 原项目的“真实形态”速览（你要学习的栈）

### 1.1 仓库结构（从根目录看）

- `data-agent-management/`：**后端**（Java 17 + Spring Boot 3.4.x），核心业务与 Graph 工作流在这里
- `data-agent-frontend/`：**前端**（Vue 3 + Vite + Element Plus + ECharts）
- `docker-file/`：Dockerfile + `docker-compose.yml`（提供 MySQL、模拟数据源等容器编排）
- `docs/`：Quick Start、Developer Guide、架构/高级功能等文档
- `vectorstore/`：默认 `SimpleVectorStore` 的本地序列化目录（项目中默认 `./vectorstore/vectorstore.json`）

### 1.2 后端关键技术点（你会在代码里见到）

- Web 框架：Spring Boot + **Spring WebFlux**（反应式、SSE 流式输出）
- AI/Agent：Spring AI + Spring AI Alibaba Graph（`StateGraph`/`CompiledGraph`/`NodeAction`）
- 数据访问：MyBatis + Druid DataSource（管理端业务库，注意：它不是被分析的业务库本身）
- 向量库：Spring AI VectorStore（默认 `SimpleVectorStore`，可扩展 Elasticsearch / pgvector / Milvus 等）
- 可观测性：OpenTelemetry（代码里集成了 Langfuse 追踪上报）
- 扩展协议：MCP Server（`spring-ai-starter-mcp-server-webflux`，对外提供 Tool Server 能力）

### 1.3 前端关键技术点

- Vue 3 + Vite
- Element Plus 组件库
- ECharts 图表（报表可视化）
- axios 调后端 API；并通过 SSE 接收流式事件

---

## 2. 把“一个请求”在原项目里跑一遍：代码阅读主线

下面这条主线是你做 MVP 时最值得复刻的链路（建议按顺序打开文件阅读）：

### 2.1 入口与 Web 层（SSE 接口）

- `D:\GitHub\DataAgent\data-agent-management\src\main\java\com\alibaba\cloud\ai\dataagent\controller\GraphController.java`
  - `GET /api/stream/search`：SSE 输出，创建 `Sinks.Many<ServerSentEvent<GraphNodeResponse>>`
  - 断开连接时会调用 `graphService.stopStreamProcessing(threadId)`

你在 MVP 里可以先实现：

- `POST /api/nl2sql`（非流式 JSON 返回）  
- 然后再补 `GET /api/stream/nl2sql`（SSE，把 token/阶段性文本流式推给前端或 curl）

### 2.2 Service 层（Graph 的编排与线程/上下文管理）

- `D:\GitHub\DataAgent\data-agent-management\src\main\java\com\alibaba\cloud\ai\dataagent\service\graph\GraphServiceImpl.java`
  - `compiledGraph = stateGraph.compile(...)`
  - `nl2sql(...)`：非流式直接 `invoke`，拿 `OverAllState` 里的 `SQL_GENERATE_OUTPUT`
  - `graphStreamProcess(...)`：流式执行、threadId 管理、多轮上下文、Human feedback 继续跑图

MVP 里建议先只保留：

- `nl2sql(query)`：直接编译图后调用 `invoke`
- 不做 `threadId` 续跑/多轮上下文（第二阶段再加）

### 2.3 Graph 配置（核心：StateGraph + Node + Dispatcher）

- `D:\GitHub\DataAgent\data-agent-management\src\main\java\com\alibaba\cloud\ai\dataagent\config\DataAgentConfiguration.java`
  - `StateGraph` 的节点定义与边（含 conditional edges）
  - 你能直观看到整条工作流：Intent → Evidence → Schema → Planner → Sql/Python → Report → END

MVP 里你可以把图缩到 2~3 个节点，例如：

1. `IntentRecognitionNode`（可先硬编码“数据分析”）
2. `SqlGenerateNode`（核心：调用 LLM 生成 SQL）
3. `SqlExecuteNode`（可选：把 SQL 在 H2 上跑一下）

### 2.4 Node（每个节点“怎么写”）

建议先读两个最典型的节点（都在 `workflow/node`）：

- `IntentRecognitionNode`：如何构建 prompt、如何把 LLM 的输出包装成图的 streaming generator
- `SqlGenerateNode`：如何处理重试、如何收集 SQL token 流并最终落到 state 里

节点目录：

- `D:\GitHub\DataAgent\data-agent-management\src\main\java\com\alibaba\cloud\ai\dataagent\workflow\node\`

### 2.5 LLM Service（模型调用的统一封装）

后端把模型调用做了统一抽象（你做 MVP 时也应该先抽象一层，便于后续换模型/换供应商）：

- 关注包：`service/llm/`、`service/aimodelconfig/`
- 你做 MVP 时：先实现一个 `LlmService` 接口
  - `callUser(prompt): Flux<ChatResponse>`（为 SSE/流式准备）
  - 或先 `call(prompt): String`（最小可运行）

---

## 3. 一张“学习地图”：从哪块学起最省力

下面是我建议的学习顺序（每一步都以“能运行/能验证”为完成标准）：

### 阶段 A：先跑起来（不改代码）

1. 后端能启动  
   - 用 H2：优先参考 `application-h2.yml` 的思路（内存库 + init sql）
2. Swagger/OpenAPI 能打开（WebFlux UI）  
3. `GET /echo/ok` 能通（健康检查）

完成标准：你能在本机把后端跑起来，并用 curl 打通一个最简单接口。

### 阶段 B：看懂“Graph 是怎么跑的”

1. 从 `GraphController` → `GraphServiceImpl` → `DataAgentConfiguration` 把调用链串起来  
2. 画出你自己的简化时序图（哪一步调用 LLM、哪一步查库、state 里塞了哪些 key）

完成标准：你能指出“一个 query 进入后在哪些节点被消费/产出”。

### 阶段 C：能生成 SQL（先不执行）

1. 只保留一个 `nl2sql` 图  
2. LLM 调用先支持 OpenAI 兼容接口（或 FakeLLM）  
3. 返回 SQL 字符串即可

完成标准：`POST /api/nl2sql` 返回一条 SQL。

### 阶段 D：执行 SQL（并返回结果）

1. 引入 H2 初始化数据  
2. 把 SQL 在 H2 上执行（JDBC/DatabaseClient 均可；MVP 推荐最直接的 JDBC）
3. 输出：SQL + rows（前 50 行）+ columns

完成标准：能看到真实表数据的查询结果。

### 阶段 E：再把“流式体验”补上（SSE）

1. SSE endpoint：把 LLM token/节点进度作为 event 推送  
2. 前端可先不用，`curl` 直接看 SSE 也行

完成标准：能边生成边输出（哪怕只是文本进度）。

### 阶段 F：按价值逐项补齐原项目能力

按“学习收益/实现复杂度”排序：

1. 多轮上下文（threadId + history）  
2. RAG（SimpleVectorStore → 业务术语/知识的 recall）  
3. Human feedback（interrupt/resume）  
4. Python executor（local/docker 两套执行器）  
5. Report generator（Markdown/HTML + ECharts option）  
6. MCP server（把 NL2SQL 作为工具暴露给外部客户端）
7. Langfuse/OpenTelemetry（追踪 token、span、链路）

---

## 4. DataAgent-mini 的工程拆解（你在 mini 项目里应该“复刻什么”）

### 4.1 建议的最小目录结构

在 `D:\GitHub\DataAgent-mini`（新仓库）里建议先只做后端：

```
dataagent-mini/
  backend/
    pom.xml
    src/main/java/... (Spring Boot WebFlux)
    src/main/resources/
      application.yml
      application-h2.yml
      sql/ (schema + data)
  docs/
    ROADMAP.md (本文件拷贝过去并持续更新)
```

> 说明：先把后端闭环跑通，再决定是否加 `frontend/`。

### 4.2 MVP 的“类/模块对照表”（从原项目映射）

| 目的 | 原项目位置（DataAgent） | mini 里建议怎么做 |
|---|---|---|
| 启动类 | `DataAgentApplication.java` | 保留同样结构 |
| HTTP 接口 | `controller/GraphController.java` | 先做 `Nl2SqlController`（JSON），再做 `SseController` |
| Graph 编排 | `config/DataAgentConfiguration.java` | 新建 `MiniGraphConfig`（2~3 节点） |
| Graph 执行 | `service/graph/GraphServiceImpl.java` | 新建 `MiniGraphService`（先不做 thread 管理） |
| 生成 SQL | `workflow/node/SqlGenerateNode.java` | mini 里保留“prompt → LLM → SQL”最小逻辑 |
| LLM 抽象 | `service/llm/*` | mini 里先做 `LlmClient` 接口 + `OpenAiCompatibleClient` |
| 数据执行 | `workflow/node/SqlExecuteNode.java` | mini 里可以用 `JdbcTemplate` / 直接 JDBC |

---

## 5. MVP 逐步实现清单（照着做就能落地）

> 建议你把这里当作 TODO 列表，每完成一项就在 mini 项目里写下“验收证据”（curl 命令 + 输出示例）。

### Step 1：初始化工程

- [ ] Java 17 + Maven 工程（Spring Boot 3.4.x）
- [ ] WebFlux starter + actuator
- [ ] H2 + 初始化 SQL（仿照原项目 `application-h2.yml`）

验收：

- [ ] `GET /actuator/health` 返回 UP

### Step 2：实现一个最小 NL2SQL 接口（非流式）

- [ ] `POST /api/nl2sql` 输入：`{ "query": "..." }`
- [ ] 输出：`{ "sql": "select ..." }`
- [ ] LLM 先用 FakeLLM（固定 SQL）也可以

验收：

- [ ] curl 能拿到 SQL

### Step 3：接入真实 LLM（OpenAI 兼容）

- [ ] 支持配置 `baseUrl`、`apiKey`、`model`
- [ ] 把 prompt 与响应日志打出来（便于学习）

验收：

- [ ] 能生成符合 H2/SQL 方言的查询

### Step 4：执行 SQL 并返回结果

- [ ] 在 H2 上执行生成的 SQL
- [ ] 返回 `columns` + `rows`（限制行数）

验收：

- [ ] 接口能返回真实查询结果

### Step 5：加 SSE（流式输出体验）

- [ ] `GET /api/stream/nl2sql?query=...`（或 POST + SSE）
- [ ] 事件：`progress` / `token` / `complete` / `error`

验收：

- [ ] 用 curl 能看到逐步输出

---

## 6. 你在 mini 项目里“应该刻意学会”的知识点（按优先级）

1. **WebFlux + SSE**：如何正确设置 `TEXT_EVENT_STREAM`、如何处理断开与资源释放  
2. **Graph/State 设计**：节点输入输出如何通过 state key 串联；如何做 conditional edge/重试  
3. **LLM 抽象层**：如何做到“供应商无关”（OpenAI 兼容是关键）  
4. **Prompt 工程**：prompt 模板、结构化输出（JSON/SQL）、错误恢复  
5. **数据库方言与安全**：限制只读查询、行数限制、SQL 注入/危险语句拦截（后置但必须补）  
6. **可观测性**：token 统计、trace/span、关键指标（后置）

---

## 7. 下一步（我建议我来做的）

如果你确认要继续，我可以直接在当前仓库里先产出一个 `DataAgent-mini` 的“脚手架草案”（仅文档 + 目录结构 + MVP 的最小后端代码），然后你把它拷贝到 `D:\GitHub\DataAgent-mini`：

- 产出：`docs/DATAAGENT_MINI_SCAFFOLD/`（或单独一个 `mini-backend/` 目录）
- 特点：不依赖 MySQL、默认 H2、提供 `POST /api/nl2sql`，可选 SSE

你希望 mini 的第一版包含哪些能力：只 NL2SQL，还是要把“SQL 执行 + 返回表格结果”也做进去？

