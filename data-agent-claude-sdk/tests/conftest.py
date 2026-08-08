from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_AGENT_CONTROL_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'control.db'}")
    monkeypatch.setenv("DATA_AGENT_RESULT_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("DATA_AGENT_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    monkeypatch.setenv("DATA_AGENT_KNOWLEDGE_DIR", str(tmp_path / "knowledge"))
    monkeypatch.setenv("DATA_AGENT_PRODUCT_DATABASE_URL", "")
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_BASE_URL", "")
    monkeypatch.setenv("DATA_AGENT_ANTHROPIC_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
