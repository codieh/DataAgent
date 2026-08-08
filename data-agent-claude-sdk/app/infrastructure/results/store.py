"""完整查询结果文件存储。

结果文件不进入 Agent 上下文。模型收到的是有限预览、统计信息和不透明的
``result_ref``，后续通过 ``inspect_result`` 分页读取。
"""

import csv
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.domain.errors import ResourceNotFoundError
from app.domain.models import QueryResult, TenantContext


class ResultStore:
    def __init__(self, root: Path | None = None):
        self.root = root or get_settings().result_dir
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, context: TenantContext, result: QueryResult) -> tuple[str, Path]:
        result_id = f"result_{uuid4().hex}"
        directory = self.root / context.tenant_id / context.conversation_id / context.run_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{result_id}.json"
        payload = {
            "result_id": result_id,
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        csv_path = path.with_suffix(".csv")
        with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=result.columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(result.rows)
        return result_id, path

    async def read(
        self,
        path: str | Path,
        *,
        offset: int = 0,
        limit: int = 50,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        result_path = Path(path)
        if not result_path.is_file():
            raise ResourceNotFoundError("result_file", str(result_path))
        data = json.loads(result_path.read_text(encoding="utf-8"))
        all_columns = list(data["columns"])
        selected_columns = [column for column in (columns or all_columns) if column in all_columns]
        if columns and len(selected_columns) != len(columns):
            missing = sorted(set(columns) - set(selected_columns))
            raise ValueError(f"结果中不存在字段：{', '.join(missing)}")
        rows = data["rows"][max(offset, 0) : max(offset, 0) + min(max(limit, 1), 500)]
        return {
            "result_id": data["result_id"],
            "columns": selected_columns,
            "rows": [{column: row.get(column) for column in selected_columns} for row in rows],
            "offset": max(offset, 0),
            "limit": min(max(limit, 1), 500),
            "row_count": data["row_count"],
            "truncated": data["truncated"],
            "next_cursor": (
                str(max(offset, 0) + len(rows)) if max(offset, 0) + len(rows) < len(data["rows"]) else None
            ),
        }

    async def read_all(self, path: str | Path, *, max_rows: int) -> dict[str, Any]:
        """读取本次 SQL 已保存的完整结果，供受限分析器使用。"""
        result_path = Path(path)
        if not result_path.is_file():
            raise ResourceNotFoundError("result_file", str(result_path))
        data = json.loads(result_path.read_text(encoding="utf-8"))
        rows = list(data.get("rows") or [])
        if len(rows) > max_rows:
            raise ValueError(f"分析输入超过允许的 {max_rows} 行")
        return {
            "result_id": data["result_id"],
            "columns": list(data.get("columns") or []),
            "rows": rows,
            "row_count": data.get("row_count", len(rows)),
            "truncated": bool(data.get("truncated", False)),
        }

    async def save_artifact(self, context: TenantContext, kind: str, payload: dict[str, Any]) -> tuple[str, Path]:
        artifact_id = f"artifact_{uuid4().hex}"
        directory = self.root / context.tenant_id / context.conversation_id / context.run_id / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{artifact_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        return artifact_id, path
