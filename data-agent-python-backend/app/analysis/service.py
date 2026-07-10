"""Python 分析服务。

端到端驱动「自然语言目标 -> LLM 生成 Python 代码 -> 沙箱安全执行 -> 结果校验」：

1. 从 SQL 查询结果中挑选/裁剪数据集，把数据文件准备好供沙箱读取；
2. 调用 LLM 生成分析代码，并做静态安全校验（白名单导入、禁用危险调用、限定文件访问）；
3. 在沙箱中执行代码，回读 result.json 并规范化结果结构；
4. 失败时把错误信息回填给 LLM 进行最多 ``max_repairs`` 次自我修复重试。

模块顶层常量定义了代码静态检查的「安全边界」，任何越界代码都会在执行前被拒绝。
"""

import ast
import csv
import json
import logging
import math
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.analysis.sandbox import PythonSandbox, SandboxExecutionError
from app.config import Settings
from app.workflow.outputs import PythonCodeOutput
from app.workflow.ports import LlmClient
from app.workflow.prompts import PYTHON_ANALYSIS_SYSTEM

logger = logging.getLogger(__name__)

# 允许导入的模块白名单，超出范围的 import 会被静态校验拦截
_ALLOWED_IMPORTS = {"collections", "datetime", "json", "math", "numpy", "pandas", "statistics"}
# 禁止调用的内置函数/危险入口，防止代码逃逸或交互阻塞
_BLOCKED_CALLS = {"breakpoint", "compile", "eval", "exec", "globals", "input", "locals", "vars", "__import__"}
# 脚本仅被允许访问这两个约定路径，杜绝任意文件读写
_ALLOWED_FILES = {"/workspace/input/data.json", "/workspace/output/result.json"}


class PythonAnalysisService:
    """编排 Python 分析的生成、校验、执行与自愈重试。"""

    def __init__(self, settings: Settings, llm: LlmClient, sandbox: PythonSandbox):
        self.settings = settings
        self.llm = llm
        self.sandbox = sandbox

    async def analyze(
        self,
        *,
        run_id: str,
        objective: str,
        query_results: list[dict[str, Any]],
        dataset_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """执行一次完整的 Python 分析。

        参数：
            run_id：所属运行 ID，用于隔离工作目录。
            objective：分析目标（自然语言）。
            query_results：上游 SQL 查询产出的结果集列表。
            dataset_ids：可选，限定只分析其中部分数据集。

        返回：包含分析 ID、代码、解释、规范化结果、日志、耗时等信息的字典。
        异常：无可用数据集、输入超限、连续重试仍失败时抛出 ValueError / SandboxExecutionError。
        """
        datasets = self._select_datasets(query_results, dataset_ids)
        if not datasets:
            raise ValueError("没有可供 Python 分析的 SQL 查询结果")
        analysis_id = f"python_{uuid4().hex}"
        # 每次分析使用独立工作目录，避免互相污染
        work_dir = self.settings.python_analysis_dir / run_id / analysis_id
        input_dir = work_dir / "input"
        output_dir = work_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        prepared = self._prepare_input_files(datasets, input_dir)
        data_path = input_dir / "data.json"
        # 把数据集元信息与样例打包成 data.json，供沙箱内脚本读取
        data_path.write_text(json.dumps({"datasets": prepared}, ensure_ascii=False, default=str), encoding="utf-8")

        # 总尝试次数 = 首次 + 配置允许的最大修复次数
        error = ""
        attempts = self.settings.python_analysis_max_repairs + 1
        for attempt in range(1, attempts + 1):
            try:
                generated = await self._generate_code(objective, prepared, error)
                code = generated.code.strip()
                validate_python_code(code)
                # 生成的代码故意用 .python 后缀而非 .py，避免 uvicorn --reload 因文件变更误重启 API
                code_path = work_dir / f"analysis-{attempt}.python"
                code_path.write_text(code, encoding="utf-8")
                result_path = output_dir / "result.json"
                result_path.unlink(missing_ok=True)
                execution = await self.sandbox.execute(
                    code_path=code_path,
                    input_dir=input_dir,
                    output_dir=output_dir,
                )
                # 约定脚本必须把结果写入 /workspace/output/result.json
                if not result_path.exists():
                    raise SandboxExecutionError("脚本没有生成 /workspace/output/result.json")
                result = validate_analysis_result(json.loads(result_path.read_text(encoding="utf-8")))
                return {
                    "id": analysis_id,
                    "objective": objective,
                    "attempt": attempt,
                    "code": code,
                    "explanation": generated.explanation,
                    "result": result,
                    "logs": {"stdout": execution.stdout, "stderr": execution.stderr},
                    "durationMs": execution.duration_ms,
                    "inputRows": sum(int(dataset["rowCount"]) for dataset in prepared),
                    "workDir": str(work_dir),
                }
            except (SandboxExecutionError, json.JSONDecodeError, SyntaxError, ValueError) as exc:
                # 仅捕获「可重试」的失败类型，把错误尾部回传给 LLM 用于下轮修复
                error = str(exc)[-self.settings.python_analysis_log_chars :]
                logger.warning(
                    "python analysis attempt failed: runId=%s analysisId=%s attempt=%d error=%s",
                    run_id,
                    analysis_id,
                    attempt,
                    error,
                )
                if attempt >= attempts:
                    raise SandboxExecutionError(
                        f"Python 分析连续失败 {attempts} 次：{error}"
                    ) from exc
        raise SandboxExecutionError("Python 分析未完成")

    async def _generate_code(
        self, objective: str, datasets: list[dict[str, Any]], previous_error: str
    ) -> PythonCodeOutput:
        """调用 LLM 生成分析代码，并把上一轮错误（若有）作为上下文传入以驱动自愈。"""
        payload = {
            "objective": objective,
            "datasets": [
                {
                    "name": dataset["name"],
                    "columns": dataset["columns"],
                    "rowCount": dataset["rowCount"],
                    "file": dataset["file"],
                    "sampleRows": dataset["sampleRows"],
                }
                for dataset in datasets
            ],
            # 首轮为空，重试时携带上一轮报错，引导模型修正
            "previousError": previous_error,
        }
        return await self.llm.complete_model(
            PythonCodeOutput,
            PYTHON_ANALYSIS_SYSTEM,
            json.dumps(payload, ensure_ascii=False, default=str),
        )

    def _select_datasets(
        self, query_results: list[dict[str, Any]], dataset_ids: list[str] | None
    ) -> list[dict[str, Any]]:
        """从查询结果中筛选数据集，并累计总行数防止输入过大。

        若指定了 ``dataset_ids`` 则只保留命中的数据集；同时在累加过程中
        检查是否超过 ``python_analysis_max_rows`` 上限，超限即报错。
        """
        allowed_ids = set(dataset_ids or [])
        datasets = []
        total_rows = 0
        for index, result in enumerate(query_results):
            dataset = result.get("dataset", {})
            # 兼容多种来源字段命名，统一解析数据集 ID
            dataset_id = str(result.get("datasetId") or dataset.get("id") or "")
            if allowed_ids and dataset_id not in allowed_ids:
                continue
            # 行数优先取显式 rowCount，否则退化为实际 rows 长度
            row_count = int(dataset.get("rowCount") or result.get("rowCount") or len(result.get("rows", [])))
            total_rows += row_count
            if total_rows > self.settings.python_analysis_max_rows:
                raise ValueError(
                    f"Python 分析输入超过 {self.settings.python_analysis_max_rows} 行，请先用 SQL 缩小范围"
                )
            datasets.append(
                {
                    "name": f"dataset_{index}",
                    "id": dataset_id,
                    "sql": result.get("sql", ""),
                    "columns": result.get("columns", []),
                    "rowCount": row_count,
                    "sampleRows": result.get("rows", [])[:5],
                    "filePath": dataset.get("filePath"),
                }
            )
        return datasets

    def _prepare_input_files(
        self, datasets: list[dict[str, Any]], input_dir: Path
    ) -> list[dict[str, Any]]:
        """为每个数据集在 input 目录准备数据文件（优先用 CSV 全量，否则写预览）。"""
        prepared = []
        for index, dataset in enumerate(datasets):
            filename = f"dataset_{index}.csv"
            target = input_dir / filename
            source = Path(dataset["filePath"]) if dataset.get("filePath") else None
            if source and source.exists():
                # 存在完整 CSV 时直接拷贝，保留全量数据
                shutil.copyfile(source, target)
            else:
                # 仅 SQLite 预览时，把前若干行写出为 CSV 供脚本使用
                _write_preview_csv(target, dataset["columns"], dataset["sampleRows"])
            prepared.append(
                {
                    **dataset,
                    "hostPath": str(target),
                    "file": f"/workspace/input/{filename}",  # 沙箱内的挂载路径
                }
            )
        return prepared


def validate_python_code(code: str) -> None:
    """静态安全校验：解析 AST 并拦截越权导入、危险调用与越界文件访问。

    任何违反安全边界的代码都会抛出 ValueError，确保不进入沙箱执行。
    """
    if not code:
        raise ValueError("模型没有生成 Python 代码")
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        raise ValueError(f"Python 语法错误：{error.msg}") from error
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # 取顶层模块名（忽略子模块后缀）做白名单比对
            modules = [alias.name.split(".", 1)[0] for alias in node.names] if isinstance(node, ast.Import) else [
                (node.module or "").split(".", 1)[0]
            ]
            denied = [module for module in modules if module not in _ALLOWED_IMPORTS]
            if denied:
                raise ValueError(f"禁止导入模块：{', '.join(denied)}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
            raise ValueError(f"禁止调用函数：{node.func.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            # 仅当路径是字面量常量时才做校验，动态路径一律视为越界
            path = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
            if path not in _ALLOWED_FILES:
                raise ValueError("禁止访问约定目录以外的文件")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("禁止访问双下划线属性")


def validate_analysis_result(value: Any) -> dict[str, Any]:
    """把沙箱产出的 result.json 规范化成稳定的结果结构。

    为缺失字段补充默认值、为列表项补齐 id、对非法枚举值回落到安全默认，
    并过滤无穷大的浮点值，保证下游渲染不崩溃。
    """
    if not isinstance(value, dict):
        raise ValueError("Python 分析结果必须是 JSON 对象")
    normalized: dict[str, Any] = {
        "summary": str(value.get("summary") or "")[:4000],
        "metrics": [],
        "findings": [],
        "charts": [],
    }
    for index, metric in enumerate(_list(value.get("metrics"), 100), start=1):
        if not isinstance(metric, dict):
            continue
        normalized["metrics"].append(
            {
                "id": str(metric.get("id") or f"python_metric_{index}"),
                "label": str(metric.get("label") or "指标"),
                "value": _finite_json(metric.get("value")),
                "formattedValue": str(metric.get("formattedValue") or metric.get("value") or ""),
                "unit": str(metric.get("unit") or ""),
                "description": str(metric.get("description") or ""),
            }
        )
    for index, finding in enumerate(_list(value.get("findings"), 100), start=1):
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get("severity") or "info")
        normalized["findings"].append(
            {
                "id": str(finding.get("id") or f"python_finding_{index}"),
                "title": str(finding.get("title") or "分析发现"),
                "description": str(finding.get("description") or ""),
                # severity 仅允许 info/success/warning，其余统一降级为 info
                "severity": severity if severity in {"info", "success", "warning"} else "info",
                "metricIds": [str(item) for item in _list(finding.get("metricIds"), 100)],
            }
        )
    for index, chart in enumerate(_list(value.get("charts"), 20), start=1):
        if not isinstance(chart, dict):
            continue
        chart_type = str(chart.get("type") or "bar")
        normalized["charts"].append(
            {
                "id": str(chart.get("id") or f"python_chart_{index}"),
                # 图表类型限定在 line/bar/pie/scatter，否则默认 bar
                "type": chart_type if chart_type in {"line", "bar", "pie", "scatter"} else "bar",
                "title": str(chart.get("title") or "分析图表"),
                "resultSetId": "",
                "xField": str(chart.get("xField") or ""),
                "yFields": [str(item) for item in _list(chart.get("yFields"), 20)],
                "seriesField": chart.get("seriesField"),
                "data": _finite_json(_list(chart.get("data"), 1000)),
            }
        )
    return _finite_json(normalized)


def _list(value: Any, limit: int) -> list[Any]:
    """安全取列表切片：非列表返回空列表，并截断到 limit 上限。"""
    return value[:limit] if isinstance(value, list) else []


def _finite_json(value: Any) -> Any:
    """递归清理 JSON 值：把无穷大/NaN 浮点替换为 None，其余结构原样保留。"""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _finite_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite_json(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _write_preview_csv(path: Path, columns: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    """把预览行写出为 CSV，供沙箱脚本在缺少全量文件时仍能读取样本。"""
    fieldnames = [str(column.get("name")) for column in columns]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
