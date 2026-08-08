"""Python 沙箱执行层。

为 LLM 生成的 Python 分析代码提供隔离的执行环境。当前实现基于 Docker，
通过一系列安全加固参数（无网络、只读根文件系统、降权用户、资源限额、禁止提权）
保证不可信代码不会对宿主机造成影响。模块同时定义了执行结果的不可变数据结构
与沙箱协议（Protocol），便于后续替换其他后端实现。
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import Settings


class SandboxExecutionError(RuntimeError):
    """沙箱执行失败（超时、缺少 Docker、脚本非零退出等）时抛出。"""


@dataclass(frozen=True)
class SandboxExecution:
    """单次沙箱执行的不可变结果快照。"""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class PythonSandbox(Protocol):
    """沙箱执行协议：约定任意后端都必须实现的 execute 接口。"""

    async def execute(self, *, code_path: Path, input_dir: Path, output_dir: Path) -> SandboxExecution: ...


class DockerPythonSandbox:
    """Runs generated analysis code in a short-lived, networkless container."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def execute(self, *, code_path: Path, input_dir: Path, output_dir: Path) -> SandboxExecution:
        """在一次性 Docker 容器中执行分析脚本。"""
        output_dir.mkdir(parents=True, exist_ok=True)
        # 输出目录需可写并允许容器内非 root 用户访问
        output_dir.chmod(0o777)
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",  # 完全禁用网络，防止脚本外联
            "--memory",
            self.settings.python_sandbox_memory,
            "--cpus",
            str(self.settings.python_sandbox_cpus),
            "--pids-limit",
            str(self.settings.python_sandbox_pids_limit),  # 限制进程数，遏制 fork 炸弹
            "--read-only",  # 根文件系统只读，写入只能通过挂载点
            "--cap-drop",
            "ALL",  # 丢弃全部 Linux 能力
            "--security-opt",
            "no-new-privileges",  # 禁止通过 setuid 提权
            "--user",
            "65534:65534",  # 以 nobody 身份运行，最小权限
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",  # 临时空间：不可执行、限大小
            "-v",
            f"{code_path.resolve()}:/workspace/analysis.py:ro",  # 代码只读挂载
            "-v",
            f"{input_dir.resolve()}:/workspace/input:ro",  # 输入只读挂载
            "-v",
            f"{output_dir.resolve()}:/workspace/output:rw",  # 输出可写挂载
            self.settings.python_sandbox_image,
            "python",
            "-B",  # 禁用 .pyc 缓存写入
            "/workspace/analysis.py",
        ]
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # 等待执行结束并施加总超时，防止容器长时间挂起
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.settings.python_sandbox_timeout_seconds
            )
        except TimeoutError as error:
            # 超时后需要先杀掉可能仍在运行的容器进程再报错
            if "process" in locals():
                process.kill()
                await process.communicate()
            raise SandboxExecutionError(
                f"Python 分析执行超过 {self.settings.python_sandbox_timeout_seconds} 秒"
            ) from error
        except FileNotFoundError as error:
            # docker 命令不存在（未安装/未在 PATH）
            raise SandboxExecutionError("未找到 Docker，请先安装并启动 Docker Desktop 或 OrbStack") from error
        duration_ms = int((loop.time() - started) * 1000)
        limit = self.settings.python_analysis_log_chars
        execution = SandboxExecution(
            exit_code=process.returncode or 0,
            # 仅保留末尾若干字符的日志，避免把超大输出回传上层
            stdout=stdout.decode("utf-8", errors="replace")[-limit:],
            stderr=stderr.decode("utf-8", errors="replace")[-limit:],
            duration_ms=duration_ms,
        )
        if execution.exit_code != 0:
            # 优先用 stderr 暴露真实错误，其次 stdout，最后用退出码兜底
            detail = execution.stderr or execution.stdout or f"exit code {execution.exit_code}"
            raise SandboxExecutionError(detail)
        return execution


def create_python_sandbox(settings: Settings) -> PythonSandbox:
    """按配置创建沙箱实例（当前仅支持 docker 后端）。"""
    if settings.python_sandbox_backend == "docker":
        return DockerPythonSandbox(settings)
    raise ValueError(f"unsupported Python sandbox backend: {settings.python_sandbox_backend}")
