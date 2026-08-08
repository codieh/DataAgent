from app.domain.errors import ConfigurationError


def test_empty_agent_result_is_treated_as_failure():
    error = ConfigurationError("Agent 未生成最终结果；请查看工具失败事件和运行日志。")

    assert error.code == "configuration_error"
    assert "未生成最终结果" in error.message
