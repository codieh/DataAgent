"""通过 Docker/OrbStack 执行模型生成的 Python 分析代码。

宿主进程不执行模型代码。容器只接收结果数据和分析脚本，禁止网络访问，并且
使用只读根文件系统、非 root 用户、资源上限和明确的超时。
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any


class PythonSandbox:
    def __init__(self, image: str, timeout_seconds: int):
        self.image = image
        self.timeout_seconds = timeout_seconds

    async def run(self, data: dict[str, Any], code: str) -> dict[str, Any]:
        script = code.strip()
        if not script:
            raise ValueError("Python 分析代码不能为空")
        if len(script) > 100_000:
            raise ValueError("Python 分析代码不能超过 100000 个字符")

        with tempfile.TemporaryDirectory(prefix="data-agent-python-") as directory:
            root = Path(directory)
            input_path = root / "input.json"
            code_path = root / "analysis.py"
            output_path = root / "output.json"
            input_path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
            code_path.write_text(script, encoding="utf-8")
            # 预先创建文件，避免 Docker 的 -v 语法把目标误创建成目录。
            output_path.touch()

            command = [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--read-only",
                "--user",
                "65532:65532",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit",
                "128",
                "--memory",
                "512m",
                "--cpus",
                "1",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m",
                "-v",
                f"{input_path}:/input/result.json:ro",
                "-v",
                f"{code_path}:/input/analysis.py:ro",
                "-v",
                f"{output_path}:/output/result.json:rw",
                self.image,
            ]
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as error:
                raise RuntimeError("未找到 docker 命令，请启动 Docker Desktop 或 OrbStack") from error

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), self.timeout_seconds)
            except TimeoutError as error:
                process.kill()
                await process.wait()
                raise RuntimeError(f"Python 分析超过 {self.timeout_seconds} 秒，已终止") from error

            if process.returncode != 0:
                detail = stderr.decode("utf-8", errors="replace")[-4000:]
                raise RuntimeError(f"Python 沙箱执行失败（exit={process.returncode}）：{detail}")
            if not output_path.is_file():
                detail = stdout.decode("utf-8", errors="replace")[-1000:]
                raise RuntimeError(f"Python 沙箱未生成结果文件：{detail}")
            result = json.loads(output_path.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise TypeError("Python 沙箱结果必须是 JSON 对象")
            return result
