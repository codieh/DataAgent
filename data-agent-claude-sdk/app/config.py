"""运行配置。

配置只从环境变量读取，避免把第三方 API Key 和数据库密码写进代码或日志。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATA_AGENT_",
        env_file=".env",
        extra="ignore",
    )

    control_database_url: str = "sqlite+aiosqlite:///./data/control.db"
    # 前端本地开发和静态部署使用的来源；身份通过请求头传递，不使用 Cookie。
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    # 本地开发沿用旧 Python 后端的 product_db；部署时必须通过环境变量
    # 覆盖为专用只读账号或 DATA_AGENT_TENANT_DATABASE_URLS 映射。
    product_database_url: str = "mysql+pymysql://root:admin@127.0.0.1:3306/product_db"
    # 生产环境为每个租户绑定独立只读库；本地单库模式可只配置 product_database_url。
    tenant_database_urls: dict[str, str] = Field(default_factory=dict)
    # 兼容旧 Python 后端的 LLM 配置命名。新项目内部仍统一使用
    # Anthropic Messages API 语义，第三方服务必须提供兼容该协议的接口。
    anthropic_base_url: str = Field(
        default="https://api.deepseek.com/anthropic",
        validation_alias=AliasChoices(
            "DATA_AGENT_ANTHROPIC_BASE_URL",
            "DATA_AGENT_LLM_BASE_URL",
            "OPENAI_BASE_URL",
            "LLM_BASE_URL",
        ),
    )
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "DATA_AGENT_ANTHROPIC_API_KEY",
            "DATA_AGENT_LLM_API_KEY",
            "OPENAI_API_KEY",
            "LLM_ANTHROPIC_API_KEY",
        ),
    )
    claude_model: str = Field(
        # 与旧 Python 后端的默认模型保持一致；实际部署可用
        # DATA_AGENT_LLM_MODEL 覆盖为供应商要求的 Model ID。
        default="deepseek-v4-flash",
        validation_alias=AliasChoices(
            "DATA_AGENT_CLAUDE_MODEL",
            "DATA_AGENT_LLM_MODEL",
            "OPENAI_MODEL",
        ),
    )
    result_dir: Path = Path("./data/results")
    workspace_dir: Path = Path("./data/workspaces")
    knowledge_dir: Path = Path("./data/knowledge/source")
    max_sql_rows: int = Field(
        default=50_000,
        validation_alias=AliasChoices(
            "DATA_AGENT_MAX_SQL_ROWS",
            "DATA_AGENT_SQL_ROW_LIMIT",
            "DATA_AGENT_ANALYSIS_DATASET_MAX_ROWS",
        ),
    )
    sql_timeout_seconds: int = 30
    sse_heartbeat_seconds: int = 15
    # 向 SDK 请求逐 token 的增量消息，Agent 的文本、思考和工具参数才能实时推送到前端。
    stream_partial_messages: bool = True
    # 增量事件默认只走 SSE 广播、不落库：逐 token 写 SQLite 会造成严重写放大，
    # 且每轮结束的 assistant.message 快照已经能完整恢复历史。调试时可打开。
    persist_stream_deltas: bool = False
    # 默认关闭扩展思考，避免第三方 Anthropic 兼容接口产生额外思考开销。
    # 如供应商明确支持 adaptive thinking，可通过 DATA_AGENT_THINKING_ENABLED=true 开启。
    thinking_enabled: bool = False
    max_agent_turns: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "DATA_AGENT_MAX_AGENT_TURNS",
            "DATA_AGENT_AGENT_MAX_ITERATIONS",
        ),
    )
    python_sandbox_image: str = "data-agent-python-sandbox:latest"
    python_sandbox_timeout_seconds: int = 60
    allowed_sensitive_fields: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "DATA_AGENT_ALLOWED_SENSITIVE_FIELDS",
            "DATA_AGENT_SQL_SENSITIVE_FIELDS",
        ),
    )
    otel_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("max_sql_rows")
    @classmethod
    def validate_max_sql_rows(cls, value: int) -> int:
        if value < 1 or value > 1_000_000:
            raise ValueError("max_sql_rows 必须位于 1 到 1000000 之间")
        return value

    def prepare_directories(self) -> None:
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.prepare_directories()
    return settings
