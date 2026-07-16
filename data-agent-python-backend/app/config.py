"""应用配置定义。

通过 pydantic-settings 从环境变量（前缀 ``DATA_AGENT_``）读取全部配置项，
涵盖 LLM、数据库、检索、记忆、Python 沙箱、上下文预算等。``get_settings()``
返回带缓存的单例，全项目共用同一份配置。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = PROJECT_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATA_AGENT_", extra="ignore")

    app_name: str = "DataAgent Python Backend"
    api_prefix: str = "/api/v1"
    database_url: str = f"sqlite+aiosqlite:///{PROJECT_DIR / 'data' / 'app.db'}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    workflow_step_delay_seconds: float = 0.05
    sse_heartbeat_seconds: float = 10.0
    result_page_size_max: int = 500
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DATA_AGENT_LLM_API_KEY", "OPENAI_API_KEY", "LLM_ANTHROPIC_API_KEY"),
    )
    llm_base_url: str = "https://api.kimi.com/coding/v1"
    llm_model: str = "kimi-for-coding"
    llm_temperature: float = 0.6
    max_context_size: int = 200_000
    context_compact_threshold: float = 0.8
    context_compact_preserve_ratio: float = 0.3
    context_tool_result_max_tokens: int = 20_000
    context_result_catalog_limit: int = 5
    context_result_preview_rows: int = 20
    context_history_search_limit: int = 5
    context_tool_result_keep_recent: int = 1
    context_tool_result_compact_chars: int = 2_000
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 20
    # 是否把模型原始返回（完整 JSON）写入日志；内容可能很长，排查问题时开启。
    llm_log_responses: bool = True
    # 是否把模型输入/输出的精简内容（截断后）写入日志；默认开启，便于观察
    # 模型到底“看到了什么、返回了什么”。可在生产环境关闭以降低日志量。
    llm_log_io: bool = True
    # 模型输入（system + messages）写入日志时最多保留的字符数。
    llm_log_input_chars: int = 80000
    # 模型输出（content + tool_calls）写入日志时最多保留的字符数。
    llm_log_output_chars: int = 80000
    # 工具调用返回内容写入日志时最多保留的字符数。
    tool_log_content_chars: int = 80000
    # 是否额外把后端日志写入本地文件；控制台输出仍会保留。
    log_file_enabled: bool = True
    # 日志文件路径，默认位于后端 data/logs 目录。
    log_file_path: Path = PROJECT_DIR / "data" / "logs" / "app.log"
    # 单个日志文件最大字节数，超过后自动轮转。
    log_file_max_bytes: int = 50 * 1024 * 1024
    # 保留的历史日志文件数量。
    log_file_backup_count: int = 5
    # Kimi OpenAI-compatible extension. False selects Instant mode.
    llm_thinking_enabled: bool = False
    product_database_url: str = "mysql+pymysql://root:admin@127.0.0.1:3306/product_db"
    # Safety cap for persisted raw results; UI and LLM previews are configured separately.
    sql_row_limit: int = 50_000
    sql_timeout_seconds: int = 30
    sql_enforce_read_only_session: bool = True
    prompt_max_query_chars: int = 40000
    agent_max_iterations: int = 50
    agent_max_sql_executions: int = 50
    agent_max_sql_repairs: int = 50
    agent_max_schema_searches: int = 50
    sql_sensitive_fields: str = "phone,mobile,email,id_card,idcard,salary,wage,address,bank_card"
    recall_index_dir: Path = WORKSPACE_DIR / "data" / "recall"
    knowledge_source_dir: Path = WORKSPACE_DIR / "data" / "knowledge" / "source"
    knowledge_manifest_path: Path = PROJECT_DIR / "data" / "knowledge-manifest.db"
    knowledge_chunk_size: int = 512
    knowledge_chunk_overlap: int = 64
    knowledge_tokenizer_model: str = "BAAI/bge-m3"
    retrieval_backend: str = "chroma"
    chroma_path: Path = PROJECT_DIR / "data" / "chroma"
    chroma_collection_name: str = "data_agent_knowledge"
    embedding_base_url: str = Field(
        default="http://127.0.0.1:1234",
        validation_alias=AliasChoices("DATA_AGENT_EMBEDDING_BASE_URL", "RECALL_EMBEDDING_BASE_URL"),
    )
    embedding_api_key: str = Field(
        default="sk-lm-UbOMkGK3:XCu17wunknLSYm9kFxFD",
        validation_alias=AliasChoices("DATA_AGENT_EMBEDDING_API_KEY", "RECALL_EMBEDDING_API_KEY"),
    )
    embedding_model: str = Field(
        default="text-embedding-bge-m3",
        validation_alias=AliasChoices("DATA_AGENT_EMBEDDING_MODEL", "RECALL_EMBEDDING_MODEL"),
    )
    embedding_path: str = Field(
        default="/v1/embeddings",
        validation_alias=AliasChoices("DATA_AGENT_EMBEDDING_PATH", "RECALL_EMBEDDING_PATH"),
    )
    recall_candidate_multiplier: int = 4
    recall_rrf_k: int = 10
    recall_vector_min_score: float = 0.25
    recall_schema_top_k: int = 4
    recall_schema_max_tables: int = 8
    recall_document_top_k: int = 5
    recall_evidence_top_k: int = 5
    memory_backend: str = "none"
    memory_chroma_collection_name: str = "data_agent_memory"
    memory_context_token_budget: int = 65_536
    memory_recent_token_budget: int = 49_152
    memory_retrieval_top_k: int = 6
    memory_retrieval_min_score: float = 0.2
    memory_extraction_enabled: bool = True
    memory_extraction_min_confidence: float = 0.7
    memory_extraction_max_existing: int = 30
    memory_summary_token_budget: int = 8_192
    memory_ttl_days: int = 180
    memory_max_items_per_conversation: int = 500
    core_memory_max_tokens: int = 2_000
    context_schema_token_budget: int = 65_536
    context_knowledge_token_budget: int = 32_768
    python_analysis_enabled: bool = True
    python_sandbox_backend: str = "docker"
    python_sandbox_image: str = "data-agent-python-sandbox:latest"
    python_sandbox_timeout_seconds: int = 30
    python_sandbox_memory: str = "512m"
    python_sandbox_cpus: float = 1.0
    python_sandbox_pids_limit: int = 64
    python_analysis_max_rows: int = 50_000
    python_analysis_max_repairs: int = 2
    python_analysis_log_chars: int = 8_000
    python_analysis_dir: Path = PROJECT_DIR / "data" / "python-analysis"
    analysis_dataset_dir: Path = PROJECT_DIR / "data" / "datasets"
    analysis_dataset_max_rows: int = 50_000
    analysis_dataset_preview_rows: int = 50
    analysis_dataset_ttl_hours: int = 168
    analysis_dataset_max_disk_mb: int = 512
    # 失败运行的 checkpoint 暂时保留用于排查，超过该时长后清理。
    checkpoint_failed_ttl_hours: int = 24
    # 运行中定期清理终态及孤儿 checkpoint 的间隔。
    checkpoint_cleanup_interval_seconds: int = 3600

    @model_validator(mode="after")
    def validate_context_budgets(self):
        if not 0 < self.context_compact_threshold < 1:
            raise ValueError("context_compact_threshold 必须在 0 和 1 之间")
        if not 0 < self.context_compact_preserve_ratio < 1:
            raise ValueError("context_compact_preserve_ratio 必须在 0 和 1 之间")
        reserved = (
            self.memory_context_token_budget
            + self.context_schema_token_budget
            + self.context_knowledge_token_budget
        )
        if reserved > self.max_context_size:
            raise ValueError(
                f"上下文分区预算合计 {reserved}，超过 max_context_size={self.max_context_size}"
            )
        if self.memory_recent_token_budget > self.memory_context_token_budget:
            raise ValueError("memory_recent_token_budget 不能超过 memory_context_token_budget")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def embedding_api_base(self) -> str:
        endpoint = f"{self.embedding_base_url.rstrip('/')}/{self.embedding_path.lstrip('/')}"
        return endpoint.removesuffix("/embeddings")

    @property
    def sql_sensitive_field_list(self) -> list[str]:
        return [field.strip().lower() for field in self.sql_sensitive_fields.split(",") if field.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
