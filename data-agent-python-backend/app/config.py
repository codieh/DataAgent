from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
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
    sse_poll_interval_seconds: float = 0.1
    sse_heartbeat_seconds: float = 10.0
    result_page_size_max: int = 500
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DATA_AGENT_LLM_API_KEY", "OPENAI_API_KEY", "LLM_ANTHROPIC_API_KEY"),
    )
    llm_base_url: str = "https://api.kimi.com/coding/v1"
    llm_model: str = "kimi-for-coding"
    llm_temperature: float = 0.6
    llm_max_tokens: int = 4096
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    llm_log_responses: bool = True
    # Kimi OpenAI-compatible extension. False selects Instant mode.
    llm_thinking_enabled: bool = False
    product_database_url: str = "mysql+pymysql://root:admin@127.0.0.1:3306/product_db"
    sql_row_limit: int = 200
    sql_timeout_seconds: int = 10
    prompt_max_query_chars: int = 4000
    recall_index_dir: Path = WORKSPACE_DIR / "data-agent-backend" / "data" / "recall"
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
    recall_rrf_k: int = 60
    recall_vector_min_score: float = 0.15
    recall_schema_top_k: int = 4
    recall_schema_max_tables: int = 8
    recall_document_top_k: int = 5
    recall_evidence_top_k: int = 5

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def embedding_api_base(self) -> str:
        endpoint = f"{self.embedding_base_url.rstrip('/')}/{self.embedding_path.lstrip('/')}"
        return endpoint.removesuffix("/embeddings")


@lru_cache
def get_settings() -> Settings:
    return Settings()
