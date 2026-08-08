# DataAgent Claude SDK

一个从零实现的多租户自然语言数据分析 Agent，使用 Claude Agent SDK 管理 Agent Loop，使用 MCP Tools 访问业务数据，使用系统级策略保证 SQL 安全和结果准确性。

## 架构边界

```text
Claude Agent SDK  -> Agent Loop、Session、Skill、上下文压缩
MCP Tools         -> Schema、知识、SQL、结果、记忆等真实能力
Application       -> 租户、运行、目标、结果校验、审核和 SSE
MySQL             -> 只读销售业务数据
SQLite            -> 本地控制面元数据
ResultStore       -> 完整查询结果和分析产物
```

Skill 只描述分析方法，不承担权限和安全责任。`execute_sql` 成功后，系统自动运行 `ResultVerifier`，只有目标校验通过后才允许最终总结。

## 启动

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8001
```

第三方模型必须提供 Anthropic Messages API 兼容接口，并支持 Tool Calling、流式输出和多轮 Tool Result。项目不会通过 LiteLLM 或 OpenAI SDK 做协议转换。模型 ID 默认沿用旧 Python 后端的 `deepseek-v4-flash`，也可以通过 `DATA_AGENT_LLM_MODEL` 覆盖。

如果旧 Python 后端已经通过 shell 配置了 `DATA_AGENT_LLM_API_KEY`，新后端会自动读取同一个变量，并在调用 Claude Agent SDK 时映射为 `ANTHROPIC_API_KEY`。API Key 不进入前端、不写入日志。

本地单租户开发可配置 `DATA_AGENT_PRODUCT_DATABASE_URL`。多租户部署应配置
`DATA_AGENT_TENANT_DATABASE_URLS` JSON 映射，例如：

本地默认值与旧 Python 后端一致：`mysql+pymysql://root:admin@127.0.0.1:3306/product_db`。
生产环境不要使用 root，必须通过环境变量覆盖为专用只读账号。

```dotenv
DATA_AGENT_TENANT_DATABASE_URLS={"tenant_a":"mysql://readonly:password@db-a:3306/sales","tenant_b":"mysql://readonly:password@db-b:3306/sales"}
```

配置租户映射后，未绑定的租户会在连接业务库前直接失败，不会回退到默认数据库。控制面身份头目前由上游认证网关注入，不能把客户端自填的 Header 当作生产认证方案。

`execute_sql` 的结果最多读取 `DATA_AGENT_MAX_SQL_ROWS` 行，完整的已读取结果会同时落到 JSON 和 CSV 文件，模型只收到列名、行数、前 20 行和 `result_ref`；需要更多数据时调用 `inspect_result` 分页读取，前端可通过下载接口选择 JSON 或 CSV。结果校验由 `ResultVerifier` 独立执行，不能通过 Skill 或提示词绕过。

## Python 沙箱

需要 Python 分析时，Agent 调用 `analyze_result` 并提交 `analyze(data)` 代码。代码不会在 FastAPI 进程中执行，而是运行在受限 Docker/OrbStack 容器中：无网络、只读根文件系统、非 root 用户、512 MB 内存、1 个 CPU、60 秒超时。

首次使用前构建镜像：

```bash
docker build -t data-agent-python-sandbox:latest sandbox/python
```

## API

```text
POST /api/v1/conversations
GET  /api/v1/conversations
GET  /api/v1/conversations/{conversation_id}
POST /api/v1/conversations/{conversation_id}/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/runs/{run_id}/events
POST /api/v1/runs/{run_id}/cancel
GET  /api/v1/result-sets/{result_id}
GET  /api/v1/result-sets/{result_id}/download
```

## 验证

```bash
uv run pytest
```
