# DataAgent Python Backend

The Python backend defined by `docs/python-backend-architecture-design.md`.

The runtime uses FastAPI, LangGraph, an SQLite checkpointer, the official
OpenAI Python SDK for OpenAI-compatible LLM endpoints, and a read-only
MySQL analysis connection.

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

OpenAPI is available at `http://localhost:8000/docs`.

## Test

```bash
uv run pytest
```

The default SQLite database is written to `data/app.db`. Override it with
`DATA_AGENT_DATABASE_URL`.

## Configuration

```bash
export DATA_AGENT_LLM_API_KEY="..."
export DATA_AGENT_LLM_BASE_URL="https://api.moonshot.ai/v1"
export DATA_AGENT_LLM_MODEL="kimi-k2.5"
export DATA_AGENT_PRODUCT_DATABASE_URL="mysql+pymysql://root:admin@127.0.0.1:3306/product_db"
export DATA_AGENT_RECALL_INDEX_DIR="../data-agent-backend/data/recall"
export DATA_AGENT_CHROMA_PATH="./data/chroma"
export DATA_AGENT_EMBEDDING_BASE_URL="http://127.0.0.1:1234"
export DATA_AGENT_EMBEDDING_MODEL="text-embedding-bge-m3"
```

真实分析链路为 `意图识别 -> 业务知识召回 -> 实时 Schema 读取 -> 规划 -> SQL 生成 -> 安全校验 ->
人工审核（可选）-> SQL 执行/失败修复 -> 结果总结`。业务知识召回默认读取现有 Java 后端生成的
`document-index.json` 和 `evidence-index.json`，启动时同步到嵌入式 Chroma，并使用向量检索与中文 BM25
的 RRF 融合结果；数据库表和字段始终以实时 Schema 为准。Chroma 默认数据目录为 `data/chroma`，
无需单独启动 Chroma 服务。Embedding 沿用 Java 后端的 OpenAI 兼容接口和 `text-embedding-bge-m3`
模型配置，默认地址为 `http://127.0.0.1:1234/v1/embeddings`。实时 Schema 也会转换为表级检索文档，
先用 Chroma + BM25 缩小候选表范围，再补齐直接关联表并交给模型确认，避免把整库结构直接塞入提示词。

The service deliberately fails a run with a clear configuration error when no
LLM API key is configured. Production code does not fall back to fake model
responses. Tests inject deterministic provider adapters while exercising the
real LangGraph, checkpoint, persistence, review, REST, and SSE paths.

Provider calls are isolated behind `LlmClient`. Workflow outputs are validated
as Pydantic models before entering LangGraph state; malformed model JSON cannot
silently flow into SQL generation or result rendering.

## LLM 401 troubleshooting

At startup the service logs the selected model, base URL, and whether a key is
configured without printing the key. A `401` usually means the credential does
not belong to the configured provider endpoint. The defaults expect a Moonshot
Open Platform API key:

```bash
export DATA_AGENT_LLM_API_KEY="..."
export DATA_AGENT_LLM_BASE_URL="https://api.moonshot.ai/v1"
export DATA_AGENT_LLM_MODEL="kimi-k2.5"
```

Kimi Code membership credentials or keys created for another endpoint cannot
necessarily authenticate against the Moonshot Open Platform API. LLM logs include
`runId`, operation, model, base URL, HTTP status, provider request ID, safe provider
message, duration, and token usage; prompt content and API keys are never logged.

For local debugging, complete model responses are controlled directly in
`app/config.py`:

```python
llm_log_responses: bool = True
llm_thinking_enabled: bool = False
```

This setting can expose SQL, query results, and business content in logs. Keep it
disabled outside a controlled local development environment by changing it to
`False`. API keys and request prompts are not logged by this option.

The raw response is logged at `WARNING` level as the complete SDK response JSON,
including provider-specific extension fields such as `reasoning_content`, and is
printed before finish-reason and structured-output validation. Restart the backend
after changing `config.py` because settings are created during application startup.

For Kimi-compatible endpoints, `llm_thinking_enabled=False` sends
`{"thinking":{"type":"disabled"}}` through the OpenAI SDK and selects Instant
mode. Change it to `True` only when reasoning output is intentionally required.
