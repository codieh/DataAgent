"""Docker 内的最小分析入口：只执行 analyze(data)，并写出 JSON。"""

import json
from pathlib import Path


data = json.loads(Path("/input/result.json").read_text(encoding="utf-8"))
source = Path("/input/analysis.py").read_text(encoding="utf-8")
namespace = {"__name__": "__analysis__"}
exec(compile(source, "analysis.py", "exec"), namespace, namespace)
analyze = namespace.get("analyze")
if not callable(analyze):
    raise RuntimeError("分析代码必须定义 analyze(data) 函数")
result = analyze(data)
Path("/output/result.json").write_text(
    json.dumps({"status": "success", "result": result}, ensure_ascii=False, default=str),
    encoding="utf-8",
)
