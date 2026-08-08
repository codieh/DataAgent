"""测试 Python 分析能力：数据集序列化、代码安全策略、分析结果边界与沙箱执行。

覆盖：数据库特殊类型的 JSON 安全转换、Python 代码策略（禁止 os/文件访问）、
分析结果图表数据量上限、以及 LLM 生成代码并在沙箱中执行的端到端流程。
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.analysis.sandbox import SandboxExecution
from app.analysis.datasets import _json_safe
from app.analysis.service import PythonAnalysisService, validate_analysis_result, validate_python_code
from app.config import Settings
from app.workflow.outputs import PythonCodeOutput


def test_dataset_json_safe_normalizes_database_values() -> None:
    """验证数据集中的 Decimal/date/嵌套结构能被 _json_safe 转为可 JSON 序列化的字符串形式。"""
    value = {"amount": Decimal("12.30"), "day": date(2026, 7, 7), "nested": [Decimal("1.5")]}

    assert _json_safe(value) == {
        "amount": "12.30",
        "day": "2026-07-07",
        "nested": ["1.5"],
    }


def test_python_code_policy_blocks_host_access() -> None:
    """验证代码安全策略：禁止导入系统模块（如 os）与直接文件访问，违者抛 ValueError。"""
    with pytest.raises(ValueError, match="禁止导入模块"):
        validate_python_code("import os\nos.system('whoami')")
    with pytest.raises(ValueError, match="禁止访问"):
        validate_python_code("open('/etc/passwd').read()")


def test_analysis_result_is_bounded() -> None:
    """验证分析结果中图表数据被截断到上限（1000 条），防止前端过载。"""
    result = validate_analysis_result(
        {
            "summary": "ok",
            "metrics": [],
            "findings": [],
            "charts": [{"id": "c1", "data": [{"x": index} for index in range(1100)]}],
        }
    )
    assert len(result["charts"][0]["data"]) == 1000


async def test_python_analysis_generates_and_executes_in_sandbox(tmp_path: Path) -> None:
    """验证端到端流程：LLM 生成 Python 代码，沙箱执行后产出分析结果，且第一次尝试即成功。"""
    settings = Settings(retrieval_backend="bm25", python_analysis_dir=tmp_path)

    class FakeLlm:
        async def complete_model(self, output_type, system, user):
            assert output_type is PythonCodeOutput
            return output_type(
                code=(
                    "import json\n"
                    "data = json.load(open('/workspace/input/data.json'))\n"
                    "json.dump({'summary': '完成', 'metrics': [], 'findings': [], 'charts': []}, "
                    "open('/workspace/output/result.json', 'w'), ensure_ascii=False)\n"
                )
            )

    class FakeSandbox:
        async def execute(self, *, code_path, input_dir, output_dir):
            # 代码文件应已落盘，且以非 .py 后缀保存（防直接执行）
            assert code_path.exists()
            assert code_path.suffix != ".py"
            # 读取注入到沙箱输入中的数据，验证数据文件被正确传递
            payload = json.loads((input_dir / "data.json").read_text(encoding="utf-8"))
            dataset_file = input_dir / Path(payload["datasets"][0]["file"]).name
            assert "10" in dataset_file.read_text(encoding="utf-8")
            (output_dir / "result.json").write_text(
                json.dumps({"summary": "完成", "metrics": [], "findings": [], "charts": []}),
                encoding="utf-8",
            )
            return SandboxExecution(exit_code=0, stdout="", stderr="", duration_ms=5)

    service = PythonAnalysisService(settings, FakeLlm(), FakeSandbox())
    result = await service.analyze(
        run_id="run_test",
        objective="计算总金额",
        query_results=[
            {
                "sql": "SELECT amount FROM orders",
                "columns": [{"name": "amount", "dataType": "number"}],
                "rows": [{"amount": 10}],
            }
        ],
    )

    assert result["result"]["summary"] == "完成"
    assert result["attempt"] == 1
