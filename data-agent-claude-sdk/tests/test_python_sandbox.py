import pytest

from app.infrastructure.analysis.sandbox import PythonSandbox


@pytest.mark.asyncio
async def test_python_sandbox_rejects_empty_code_without_running_docker() -> None:
    sandbox = PythonSandbox("missing-image", 1)
    with pytest.raises(ValueError, match="不能为空"):
        await sandbox.run({"rows": []}, " ")
