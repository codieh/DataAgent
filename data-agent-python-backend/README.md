# DataAgent Python Backend

DataAgent 的主后端服务，基于 FastAPI、LangGraph 和 OpenAI Python SDK 构建，为桌面端提供会话管理、Agent 分析、人工审核、结果查询和 SSE 实时事件。

## 核心能力

- 基于 LangGraph 的持久化分析工作流与 SQLite Checkpoint
- 基于 OpenAI 原生 Tool Calling 的受控 Agent 循环
- Chroma 向量检索、中文 BM25 与 RRF 混合召回
- MySQL 实时 Schema 检索和只读数据分析
- 基于 `sqlglot` AST 的确定性 SQL 安全检查
- Docker 隔离的 Python 复杂分析
- 会话历史、长期记忆和自动上下文压缩
- REST 持久化结果与可断线恢复的 SSE 事件流

## 运行要求

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- MySQL 8+
- OpenAI 兼容的 LLM 与 Embedding 服务
- Docker（仅启用 Python 复杂分析时需要）

## 本地启动

安装依赖：

```bash
uv sync
```

设置最基本的运行配置：

```bash
export DATA_AGENT_LLM_API_KEY="your-api-key"
export DATA_AGENT_LLM_BASE_URL="https://api.moonshot.ai/v1"
export DATA_AGENT_LLM_MODEL="kimi-k2.5"
export DATA_AGENT_PRODUCT_DATABASE_URL="mysql+pymysql://user:password@127.0.0.1:3306/product_db"
export DATA_AGENT_EMBEDDING_BASE_URL="http://127.0.0.1:1234"
export DATA_AGENT_EMBEDDING_MODEL="text-embedding-bge-m3"
```

启动开发服务器：

```bash
uv run uvicorn app.main:app --reload --port 8000
```

| 地址 | 用途 |
| --- | --- |
| <http://localhost:8000/docs> | OpenAPI 文档 |
| <http://localhost:8000/api/v1/health> | 服务健康检查 |
| <http://localhost:8000/api/v1/bootstrap> | 前端初始化数据 |

未配置 API Key 时，服务可以启动，但真实分析运行会返回明确的配置错误，不会降级到虚假模型结果。

## 初始化演示数据

项目提供独立的离线 CLI，可生成包含地区、渠道、会员、商品、订单、营销活动和退款的电商数据。演示库使用 7 张业务表，地区和渠道直接保存在用户或订单中，不额外创建小型字典表。CLI 不会随后端自动运行。

先预览生成规模：

```bash
uv run python -m scripts.demo_data.generate --preset medium --dry-run
```

确认后重建本地演示表并写入数据：

```bash
uv run python -m scripts.demo_data.generate \
  --database-url "mysql+pymysql://user:password@127.0.0.1:3306/product_db" \
  --preset medium \
  --reset
```

默认 `medium` 规模包含 5,000 个用户、200 个商品和 50,000 笔订单。完整参数、数据规律和安全说明见 [`scripts/demo_data/README.md`](./scripts/demo_data/README.md)。

## 分析流程

```mermaid
flowchart TD
    INPUT["用户问题"] --> GUARD["输入安全检查"]
    GUARD --> AGENT["统一 Agent Tool Loop"]
    AGENT --> CHAT["直接回答"]
    AGENT --> HISTORY["历史会话检索"]
    AGENT --> MEMORY["核心记忆改写"]
    AGENT --> SCHEMA["Schema 检索"]
    AGENT --> KNOWLEDGE["业务知识检索"]
    AGENT --> SQL["候选 SQL"]
    SQL --> POLICY["sqlglot 安全检查"]
    POLICY --> REVIEW{"需要人工审核?"}
    REVIEW -->|"是"| PAUSE["暂停并等待审核"]
    PAUSE --> EXECUTE["只读 SQL 执行"]
    REVIEW -->|"否"| EXECUTE
    EXECUTE --> PYTHON["可选 Python 分析"]
    PYTHON --> RESULT["结构化结果总结"]
```

Agent 默认最多循环 6 次、执行 3 条 SQL、修复 2 次 SQL。限制可在 `app/config.py` 中调整，避免开放式循环无限消耗时间和 Token。

## 上下文管理

每次分析开始前，`ContextBuilder` 会读取 SQLite 中的会话摘要和尚未摘要的消息，并按统一预算判断是否需要持久化压缩：

1. 会话摘要与尚未摘要消息达到记忆预算的 `80%` 时触发压缩。
2. 较早消息交给 `ConversationSummarizer` 合并，最近约 `30%` 保留原文。
3. 摘要和覆盖到的消息游标写入 SQLite，后续请求直接复用。
4. 已由摘要覆盖的原始消息不再重复加入最近对话；历史会话通过 SQLite FTS5 工具按需搜索，不写入 Chroma。
5. 用户核心记忆以一份精简 Markdown 保存，新建会话时作为隐藏 System Message 加入；用户明确要求修改时由 `rewrite_core_memory` 整块改写。
6. LLM Client 不再创建第二份临时摘要，只截断超大 Tool Result 并执行最终硬上限检查。

默认总上下文上限为 `200000`，其中会预留模型输出和安全余量。持久化摘要实现在 `app/memory/summary.py`，最终请求保护位于 `app/infrastructure/llm/openai.py`。

模型调用的工具名称、完整参数和模型实际看到的 ToolMessage 会写入 SQLite `tool_calls` 表；大型 SQL 数据仍由 `result_sets` 和 CSV 保存，工具轨迹记录对应引用。

## 知识召回

业务人员维护的 TXT、Markdown 文档放在仓库根目录的 `data/knowledge/source`。文档通过独立命令增量写入嵌入式 Chroma，不会在请求期间重新切块或计算文档向量：

```bash
cd data-agent-python-backend
uv run data-agent-index-knowledge
```

索引器先按 Markdown 标题和自然段落切分，只对超过 `512 tokens` 的段落递归按句子切分，并仅在这种强制拆分场景保留 `64 tokens` 重叠。SQLite 清单记录文件和 Chunk 哈希；未变化文件直接跳过，修改与删除会同步到 Chroma。Embedding 模型或切块配置变化后执行 `uv run data-agent-index-knowledge --rebuild`。

在线检索只计算当前查询的向量，然后查询已经持久化的文档向量：

```text
查询
  ├─ Chroma 向量召回
  └─ 中文 BM25 召回
          ↓
       RRF 融合
          ↓
   Top-K 候选上下文
```

实时数据库 Schema 会转换为表级检索文档。系统先缩小候选表范围，再补充直接关联表并按需查看字段，避免将整库结构一次性放入模型上下文。Chroma 数据保存在 `data/chroma`，索引清单保存在 `data/knowledge-manifest.db`，无需单独运行向量数据库服务。

## SQL 安全

候选 SQL 在执行前必须通过确定性检查：

- 仅允许 `SELECT` 查询
- 表名、字段名必须存在于实时 Schema
- 禁止无连接条件的危险 JOIN
- 拦截敏感字段、系统函数和不受控 `SELECT *`
- 自动限制最大返回行数
- MySQL 会话只读并设置执行超时

生产或共享环境中，`DATA_AGENT_PRODUCT_DATABASE_URL` 必须使用仅拥有业务表 `SELECT` 权限的专用账号。模型判断不能替代数据库权限。

## Python 分析沙箱

首次使用前构建镜像：

```bash
docker build -t data-agent-python-sandbox:latest sandbox/python
```

默认沙箱关闭网络，以非 root 用户运行，使用只读根文件系统，并限制 CPU、内存、PID 和 30 秒执行时间。SQL 完整结果保存到 `data/datasets`，沙箱通过只读挂载访问数据文件。

默认策略：

- 单个数据集最多 5 万行
- 数据集保留 7 天
- 数据目录最大 512 MB
- SQLite 和 LangGraph State 只保存最多 200 行预览
- 代码、执行日志和分析结果保存为 `python_analysis` Artifact

## API 概览

| API | 说明 |
| --- | --- |
| `POST /api/v1/conversations` | 创建会话 |
| `GET /api/v1/conversations` | 查询历史会话 |
| `POST /api/v1/conversations/{id}/runs` | 创建分析运行 |
| `GET /api/v1/runs/{id}` | 获取完整运行快照 |
| `GET /api/v1/runs/{id}/events` | 订阅 SSE 运行事件 |
| `POST /api/v1/runs/{id}/cancel` | 取消运行 |
| `POST /api/v1/runs/{id}/retry` | 重试运行 |
| `POST /api/v1/reviews/{id}/approve` | 批准人工审核 |
| `POST /api/v1/reviews/{id}/reject` | 退回人工审核 |
| `GET /api/v1/result-sets/{id}` | 分页读取查询结果 |
| `GET /api/v1/runs/{id}/export` | 导出分析结果 |

完整请求和响应模型以 OpenAPI 文档为准。

## 配置

配置类位于 `app/config.py`，环境变量统一使用 `DATA_AGENT_` 前缀。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `DATA_AGENT_DATABASE_URL` | 本地 SQLite | 会话、运行、事件和产物 |
| `DATA_AGENT_PRODUCT_DATABASE_URL` | 本地 MySQL | 只读业务数据源 |
| `DATA_AGENT_LLM_MODEL` | `kimi-for-coding` | OpenAI 兼容模型名 |
| `DATA_AGENT_MAX_CONTEXT_SIZE` | `200000` | 总上下文窗口 |
| `DATA_AGENT_CONTEXT_COMPACT_THRESHOLD` | `0.8` | 会话记忆触发持久化摘要的比例 |
| `DATA_AGENT_CONTEXT_COMPACT_PRESERVE_RATIO` | `0.3` | 持久化摘要时保留的近期原文比例 |
| `DATA_AGENT_CONTEXT_TOOL_RESULT_MAX_TOKENS` | `20000` | 单条工具结果预算 |
| `DATA_AGENT_SQL_ROW_LIMIT` | `200` | SQL 默认最大返回行数 |
| `DATA_AGENT_SQL_TIMEOUT_SECONDS` | `10` | SQL 执行超时 |
| `DATA_AGENT_RETRIEVAL_BACKEND` | `chroma` | 知识检索实现 |

## 测试

运行完整测试：

```bash
uv run pytest
```

只运行指定模块：

```bash
uv run pytest tests/test_llm_client.py -q
```

当前测试通过依赖注入使用确定性 Provider，同时覆盖真实 LangGraph、Checkpoint、SQLite、REST、SSE、审核和安全策略链路。

## 可观测性与调试

LLM 日志包含 `runId`、操作名称、模型、请求 ID、耗时、结束原因和 Token 用量，不会记录 API Key。HTTP 请求会生成或沿用 `X-Request-ID`。

本地调试可在 `app/config.py` 中调整：

```python
llm_log_responses: bool = True
llm_thinking_enabled: bool = False
```

完整响应日志可能包含 SQL、查询结果和业务内容，只应在受控的本地环境开启。修改配置后需要重启后端。

遇到 `401` 时，请确认 API Key、`DATA_AGENT_LLM_BASE_URL` 和模型属于同一个服务端。Kimi Code 会员凭证不一定能用于 Moonshot 开放平台 API。
