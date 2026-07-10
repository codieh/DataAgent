<div align="center">
  <img src="./img/LOGO.png" alt="DataAgent Logo" width="120" />
  <h1>DataAgent</h1>
  <p>面向自然语言数据分析场景的桌面 AI Agent</p>
</div>

DataAgent 将自然语言问题转换为可审查、可执行的分析过程：检索相关表结构和业务知识，规划分析步骤，安全执行 SQL，并生成指标、图表与结论。前端通过 REST 获取持久化结果，通过 SSE 实时展示 Agent 的执行过程。

> 当前版本面向本地开发与作品演示，业务数据存储在 MySQL，应用状态存储在 SQLite，向量检索使用嵌入式 Chroma，无需单独部署向量数据库。

## 功能特性

- **自然语言数据分析**：从用户问题出发完成 Schema 检索、SQL 查询、Python 分析和结果总结。
- **受控 Agent 工具循环**：基于 LangGraph 和原生 Tool Calling，让模型按需检索表结构、查询知识并提交 SQL。
- **混合知识召回**：融合 Chroma 向量检索与中文 BM25，通过 RRF 合并候选结果。
- **多轮上下文管理**：保存会话历史与长期记忆，并在上下文接近上限时自动压缩旧消息。
- **SQL 安全治理**：使用 `sqlglot` AST 执行 SELECT Only、表字段白名单、敏感字段和行数限制等检查。
- **人工审核与故障恢复**：危险或高影响查询可暂停等待审核，运行支持取消、重试和断线恢复。
- **隔离式 Python 分析**：复杂计算在无网络、只读文件系统和资源受限的 Docker 沙箱中执行。
- **实时且可恢复的交互**：SSE 推送阶段事件，REST 提供完整结果、分页、历史会话和产物下载。

## 系统架构

```mermaid
flowchart LR
    UI["Electron + React"] -->|"REST"| API["FastAPI"]
    API -->|"SSE events"| UI
    API --> APP["Application Services"]
    APP --> GRAPH["LangGraph Agent Workflow"]
    GRAPH --> LLM["OpenAI-compatible LLM"]
    GRAPH --> RAG["BM25 + Chroma"]
    GRAPH --> SAFE["SQL Safety Policy"]
    SAFE --> MYSQL[("MySQL Business Data")]
    GRAPH --> PY["Docker Python Sandbox"]
    APP --> SQLITE[("SQLite State + Checkpoints")]
```

一次分析运行的主要流程：

```text
输入安全检查
  → 意图识别
  → Agent 工具循环
      ├─ Schema 检索与表结构查看
      ├─ 业务知识检索
      ├─ 分析计划更新
      └─ SQL 提交
  → SQL 确定性安全检查
  → 必要时人工审核
  → MySQL 查询 / Docker Python 分析
  → 结构化结果总结
```

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 桌面端 | Electron、React、TypeScript、Vite |
| API 与实时通信 | FastAPI、SSE |
| Agent 工作流 | LangGraph、OpenAI Python SDK、原生 Tool Calling |
| 应用状态 | SQLite、SQLAlchemy、LangGraph SQLite Checkpointer |
| 业务数据 | MySQL、PyMySQL |
| 知识召回 | Chroma、BM25、RRF、Embedding API |
| SQL 安全 | sqlglot AST、只读会话、查询超时 |
| Python 分析 | Docker、Pandas、受限执行环境 |

## 项目结构

```text
DataAgent/
├── data-agent-frontend/        # Electron + React 桌面端
├── data-agent-python-backend/  # FastAPI + LangGraph 后端
├── docs/                       # 架构设计、产品需求和界面参考
├── data/                       # 本地知识索引与运行数据
└── img/                        # README 与项目截图
```

## 快速开始

### 1. 环境要求

- Python 3.11+
- Node.js 18+
- MySQL 8+
- Docker（仅 Python 复杂分析需要）
- [`uv`](https://docs.astral.sh/uv/)（推荐的 Python 包管理器）

### 2. 启动 Python 后端

```bash
cd data-agent-python-backend
uv sync
```

配置 LLM、业务数据库和 Embedding 服务：

```bash
export DATA_AGENT_LLM_API_KEY="your-api-key"
export DATA_AGENT_LLM_BASE_URL="https://api.moonshot.ai/v1"
export DATA_AGENT_LLM_MODEL="kimi-k2.5"
export DATA_AGENT_PRODUCT_DATABASE_URL="mysql+pymysql://user:password@127.0.0.1:3306/product_db"
export DATA_AGENT_EMBEDDING_BASE_URL="http://127.0.0.1:1234"
export DATA_AGENT_EMBEDDING_MODEL="text-embedding-bge-m3"
```

启动服务：

```bash
uv run uvicorn app.main:app --reload --port 8000
```

首次运行可以生成一套包含用户、商品、订单、促销、渠道和退款的演示数据：

```bash
uv run python -m scripts.demo_data.generate \
  --database-url "mysql+pymysql://user:password@127.0.0.1:3306/product_db" \
  --preset medium \
  --reset
```

`--reset` 会重建演示表，执行前请确认连接的是本地演示数据库。详细参数见 [演示数据生成器文档](./data-agent-python-backend/scripts/demo_data/README.md)。

- OpenAPI：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/v1/health>

如需使用 Python 分析，先构建沙箱镜像：

```bash
docker build -t data-agent-python-sandbox:latest sandbox/python
```

### 3. 启动桌面端

```bash
cd data-agent-frontend
npm install
npm run dev
```

## 配置说明

所有后端环境变量使用 `DATA_AGENT_` 前缀，默认值和完整配置位于 [`data-agent-python-backend/app/config.py`](./data-agent-python-backend/app/config.py)。常用配置如下：

| 配置项 | 用途 | 默认值 |
| --- | --- | --- |
| `DATA_AGENT_DATABASE_URL` | 应用状态与会话数据库 | `sqlite+aiosqlite:///.../data/app.db` |
| `DATA_AGENT_PRODUCT_DATABASE_URL` | 只读业务数据库连接 | 本地 `product_db` |
| `DATA_AGENT_LLM_BASE_URL` | OpenAI 兼容接口地址 | Kimi Coding API |
| `DATA_AGENT_LLM_MODEL` | 对话模型 | `kimi-for-coding` |
| `DATA_AGENT_MAX_CONTEXT_SIZE` | 模型上下文上限 | `200000` |
| `DATA_AGENT_RETRIEVAL_BACKEND` | 知识检索后端 | `chroma` |
| `DATA_AGENT_CHROMA_PATH` | Chroma 本地目录 | `data/chroma` |
| `DATA_AGENT_SQL_ROW_LIMIT` | SQL 最大返回行数 | `200` |
| `DATA_AGENT_SQL_TIMEOUT_SECONDS` | SQL 执行超时 | `10` |

生产或共享环境中，请为业务数据库创建仅拥有目标表 `SELECT` 权限的专用账号，并关闭完整模型响应日志。

## 测试

```bash
cd data-agent-python-backend
uv run pytest
```

前端静态检查与构建：

```bash
cd data-agent-frontend
npm run lint
npm run build
```

## 文档

- [Python 后端架构设计](./docs/python-backend-architecture-design.md)
- [前端产品需求文档](./docs/前端产品需求文档.md)
- [Python 后端依赖审计](./docs/python-backend-dependency-audit.md)
- [前端界面参考](./docs/frontend-reference/README.md)
- [Python 后端详细说明](./data-agent-python-backend/README.md)
- [Python 后端消息组装说明](./docs/python-backend-message-assembly.md)

## 安全说明

DataAgent 的模型输出不会直接执行。候选 SQL 必须经过确定性 AST 检查，数据库连接也应使用最小权限账号。不过，本项目仍处于本地开发阶段，不应在未经额外鉴权、审计和隔离的情况下直接暴露到公网。

## License

详见 [LICENSE](./LICENSE)。
