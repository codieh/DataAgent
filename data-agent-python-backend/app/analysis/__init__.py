"""分析子模块的公共导出入口。

聚合 Python 分析所需的几类核心能力，供应用层与 API 层统一从这里导入，
避免在上层直接依赖具体实现类：

- ``AnalysisDatasetStore``：完整查询结果落盘（CSV）管理，仅在 SQLite 保留预览。
- ``DockerPythonSandbox`` / ``PythonSandbox`` / ``create_python_sandbox``：沙箱执行。
- ``PythonAnalysisService``：调度 LLM 生成代码、沙箱执行、结果校验。
- ``ResultHistoryService``：会话维度的历史结果检索与查看。
"""

from app.analysis.service import PythonAnalysisService
from app.analysis.sandbox import DockerPythonSandbox, PythonSandbox, create_python_sandbox
from app.analysis.datasets import AnalysisDatasetStore
from app.analysis.history import ResultHistoryService

__all__ = [
    "AnalysisDatasetStore",
    "DockerPythonSandbox",
    "PythonAnalysisService",
    "PythonSandbox",
    "ResultHistoryService",
    "create_python_sandbox",
]
