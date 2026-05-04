# Lite Backend 新电脑启动手册

这份文档用于帮助我们在**另一台电脑**上把 `data-agent-backend` 的 `lite-backend` 能力尽快跑起来。  
目标不是一次性做到最优部署，而是先完成一套：

- 能启动
- 能调试
- 能跑 SSE
- 能走 Planner / HumanFeedback / SQL / Recall

的最小可用环境。

---

## 1. 先看当前项目依赖了什么

当前 `lite-backend` 不是一个纯内存 demo，它依赖以下几类组件：

- **JDK**
- **Maven**
- **MySQL**
  - 业务 SQL 查询
- **PostgreSQL + pgvector**
  - recall 向量检索
- **本地 embedding 服务**
  - 当前默认模型：`bge-m3`
- **MiniMax / Anthropic 兼容接口的 LLM Key**
  - 用于 `intent / enhance / planner / sql generate / result`

---

## 2. 必须准备的软件环境

### 2.1 JDK

当前 `pom.xml` 里：

- `java.version=17`
- 但 `maven-compiler-plugin` 配的是：
  - `source=19`
  - `target=19`

所以**按当前仓库直接编译运行，建议安装 JDK 19**。

建议检查：

```powershell
java -version
javac -version
```

---

### 2.2 Maven

建议使用 Maven 3.9+。

检查：

```powershell
mvn -version
```

> 注意：这个项目之前遇到过 Maven 默认本地仓库路径异常的问题。  
> 如果新电脑也出现 `.part.lock` / 本地仓库路径错误，建议直接给 Maven 指定一个项目内 repo 目录。

例如：

```powershell
mvn "-Dmaven.repo.local=D:\GitHub\DataAgent\data-agent-backend\target\m2repo" -pl data-agent-backend -DskipTests compile
```

---

## 3. 必须准备的数据库

### 3.1 MySQL（业务 SQL 查询）

当前业务数据默认走：

- 数据库：`product_db`

默认配置在：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\resources\application.yml`

默认连接：

```text
jdbc:mysql://127.0.0.1:3306/product_db
```

默认账号密码：

- username: `root`
- password: `admin`

建议至少准备这些表：

- `users`
- `products`
- `orders`
- `order_items`
- `categories`
- `product_categories`

这些表是当前 schema introspect / schema recall / NL2SQL 的默认演示对象。

---

### 3.2 PostgreSQL + pgvector（Recall 向量检索）

当前 recall 向量后端已经统一切到了：

- `pgvector`

默认连接：

```text
jdbc:postgresql://127.0.0.1:5432/data_agent_recall
```

默认账号密码：

- username: `postgres`
- password: `postgres`

还需要确保：

- PostgreSQL 已安装
- `pgvector` 扩展可用

建议先在 PostgreSQL 中执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

> 当前项目里的 `PgVectorSearchService` 在运行时也会尝试 `CREATE EXTENSION IF NOT EXISTS vector`，  
> 但前提是连接账号有足够权限。新电脑上如果权限不足，最好提前手动执行。

---

## 4. 必须准备的模型服务

### 4.1 Embedding 服务

当前 recall embedding 默认配置是：

- base-url: `http://localhost:11434`
- path: `/v1/embeddings`
- model: `bge-m3`

也就是说，项目预期本地有一个**兼容 OpenAI embeddings 接口**的服务在跑。

你至少要保证：

- `POST http://localhost:11434/v1/embeddings`
- 可以正常返回 `bge-m3` 的向量

建议通过环境变量覆盖：

- `RECALL_EMBEDDING_BASE_URL`
- `RECALL_EMBEDDING_MODEL`
- `RECALL_EMBEDDING_PATH`
- `RECALL_EMBEDDING_API_KEY`（如果你的服务需要）

---

### 4.2 LLM Key

当前默认 LLM 配置在：

- `llm.anthropic.base-url=https://api.minimaxi.com/anthropic`

需要准备：

- `LLM_ANTHROPIC_API_KEY`

如果没有这个 key，当前默认 provider：

- `intent=minimax`
- `enhance=minimax`
- `sql.generate=minimax`
- `result=minimax`

都无法正常运行。

如果只是临时想跑通流程，可以把某些 provider 改成 `mock`，但这会影响真实效果验证。

---

## 5. 需要准备的本地目录

当前 `application.yml` 里有一些**Windows 绝对路径**配置。  
换电脑后，最容易踩坑的就是这里。

当前主要目录有：

- trace：
  - `D:\GitHub\DataAgent\data-agent-backend\data\traces`
- recall store：
  - `D:\GitHub\DataAgent\data-agent-backend\data\recall`
- documents：
  - `D:\GitHub\DataAgent\data-agent-backend\data\documents`

建议你做两件事里的其中一种：

### 方案 A：直接在新电脑建立相同路径

优点：

- 最省事
- 不用改配置

### 方案 B：改 `application.yml`

把这些目录改成你新电脑上的路径，例如：

- `C:\workspace\DataAgent\data-agent-backend\data\traces`
- `C:\workspace\DataAgent\data-agent-backend\data\recall`
- `C:\workspace\DataAgent\data-agent-backend\data\documents`

> 如果后面要进一步工程化，建议把这些也逐步改成环境变量配置，而不是继续写死绝对路径。

---

## 6. 建议配置的环境变量

建议新电脑上至少准备这些环境变量：

### MySQL

- `PRODUCT_DB_URL`
- `PRODUCT_DB_USERNAME`
- `PRODUCT_DB_PASSWORD`

### pgvector

- `RECALL_PGVECTOR_ENABLED`
- `RECALL_PGVECTOR_URL`
- `RECALL_PGVECTOR_USERNAME`
- `RECALL_PGVECTOR_PASSWORD`
- `RECALL_PGVECTOR_TABLE`
- `RECALL_PGVECTOR_DIMENSIONS`

### Embedding

- `RECALL_EMBEDDING_BASE_URL`
- `RECALL_EMBEDDING_API_KEY`
- `RECALL_EMBEDDING_MODEL`
- `RECALL_EMBEDDING_PATH`

### LLM

- `LLM_ANTHROPIC_API_KEY`

### 调试

- `APP_LOG_LEVEL`

---

## 7. 推荐的启动顺序

### Step 1：启动 MySQL

确认：

- `product_db` 可连接
- 默认 demo 表存在

### Step 2：启动 PostgreSQL + pgvector

确认：

- `data_agent_recall` 可连接
- `vector` 扩展存在

### Step 3：启动 embedding 服务

确认：

- `http://localhost:11434/v1/embeddings` 可用
- `bge-m3` 模型可返回向量

### Step 4：设置 LLM key

至少准备：

- `LLM_ANTHROPIC_API_KEY`

### Step 5：初始化 / 检查本地目录

确认：

- `data\recall`
- `data\documents`
- `data\traces`

这些目录存在且可写。

### Step 6：编译项目

推荐优先使用项目内 Maven 仓库路径：

```powershell
mvn "-Dmaven.repo.local=D:\GitHub\DataAgent\data-agent-backend\target\m2repo" -pl data-agent-backend -DskipTests compile
```

### Step 7：启动 backend

```powershell
mvn "-Dmaven.repo.local=D:\GitHub\DataAgent\data-agent-backend\target\m2repo" -pl data-agent-backend spring-boot:run
```

---

## 8. 启动后怎么验证

### 8.1 打开调试页

当前已经有一个轻量调试页：

- `http://localhost:8080/lite-debug.html`

它适合验证：

- SSE 是否实时
- Graph 阶段流转
- Planner / PlanExecutor
- HumanFeedback
- SQL / rows / summary / resultMode

---

### 8.2 用调试页验证最关键的几个能力

建议至少测这些：

- 普通单轮查询
- 多 step Planner 查询
- `humanReview=true`
- `Approve / Reject`
- 明显会触发 SQL Guard 的查询

---

## 9. 当前最容易踩的坑

### 9.1 JDK 版本不对

最容易出现：

- 用 JDK 17 跑
- 但编译配置是 19

所以当前最稳的是：

- **JDK 19**

---

### 9.2 `application.yml` 里的绝对路径没改

如果新电脑没有：

- `D:\GitHub\DataAgent\...`

那 trace / recall / documents 都会出问题。

---

### 9.3 pgvector 扩展没装

PostgreSQL 本身装好了，不代表 `vector` 扩展就可用。

---

### 9.4 本地 embedding 服务没起来

当前 recall 已经依赖 embedding，不起服务会直接影响：

- vector recall
- pgvector search
- bm25 + pgvector + reranker 全链路

---

### 9.5 LLM key 没配

当前默认不是 mock provider，  
所以没有 key 时：

- `intent`
- `enhance`
- `planner`
- `sql generate`
- `result`

都会受影响。

---

### 9.6 Maven 本地仓库路径问题

这个项目之前已经出现过：

- `.part.lock`
- 本地仓库路径不存在

所以新电脑建议从第一天开始就考虑：

- 使用项目内 `m2repo`

---

## 10. 最小可用版本（如果只是想先跑起来）

如果你只是想先做一轮联调，最少需要：

- JDK 19
- Maven
- MySQL
- PostgreSQL + pgvector
- embedding 服务
- `LLM_ANTHROPIC_API_KEY`

然后：

- 改好 `application.yml` 的绝对路径
- 起 `lite-debug.html`
- 走一遍 query

这就足够让当前 `lite-backend` 的主能力跑起来了。

---

## 11. 一句话总结

在其他电脑上运行当前 `lite-backend`，本质上是在准备一套：

- **JDK + Maven**
- **MySQL（业务查询）**
- **PostgreSQL + pgvector（向量召回）**
- **embedding 服务**
- **LLM key**
- **本地可写目录**

的联调环境。

当前最值得优先保障的是：

> **JDK 版本、数据库连接、pgvector 扩展、embedding 服务、以及 `application.yml` 里的本地路径。**
