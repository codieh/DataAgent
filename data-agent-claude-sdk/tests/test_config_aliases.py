from app.config import Settings


def test_settings_accepts_legacy_llm_environment_names(monkeypatch):
    # autouse fixture 会清空新命名，这里显式验证旧 Python 后端的命名仍可用。
    monkeypatch.delenv("DATA_AGENT_ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("DATA_AGENT_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("DATA_AGENT_LLM_BASE_URL", "https://provider.example/anthropic")
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "same-key-as-legacy-backend")
    monkeypatch.setenv("DATA_AGENT_LLM_MODEL", "provider-model")
    monkeypatch.setenv("DATA_AGENT_AGENT_MAX_ITERATIONS", "17")

    settings = Settings(_env_file=None)

    assert settings.anthropic_base_url == "https://provider.example/anthropic"
    assert settings.anthropic_api_key == "same-key-as-legacy-backend"
    assert settings.claude_model == "provider-model"
    assert settings.max_agent_turns == 17
