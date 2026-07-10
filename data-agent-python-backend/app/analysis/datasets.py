"""分析数据集存储。

设计目标：完整查询结果可能很大，直接全部存入 SQLite 会拖慢数据库，
因此这里采用「完整数据落盘（CSV 文件）+ SQLite 仅保留预览」的策略：

- 写入时把全量行以原子方式落盘为 CSV，并在 SQLite 的 ResultSetModel 中只存前 N 行预览。
- 读取时按需分页从 CSV 读取全量数据，SQLite 预览仅在文件缺失时作为兜底。
- 通过 TTL 与磁盘配额（按修改时间最久优先）自动清理过期/超限数据集，超限时退化为仅存 SQLite。
"""

import asyncio
import csv
import logging
import os
from datetime import date, datetime, time
from decimal import Decimal
from datetime import timedelta
from itertools import islice
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config import Settings
from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.models import ResultSetModel, utc_now
from app.infrastructure.persistence.repositories.base import new_id


logger = logging.getLogger(__name__)


class AnalysisDatasetStore:
    """完整查询结果落盘（CSV）存储，SQLite 仅保留预览行。

    负责分析数据集的创建、分页读取与磁盘/过期清理，是分析结果在持久层与应用层之间的桥梁。
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        # 提前创建数据集根目录，避免后续写文件时父目录不存在
        self.settings.analysis_dataset_dir.mkdir(parents=True, exist_ok=True)

    async def create(
        self, *, run_id: str, columns: list[dict[str, Any]], rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """创建分析数据集：全量写入 CSV 并将预览写入 SQLite。

        参数：
            run_id：所属运行 ID，用于关联来源。
            columns：列元信息（含 name、dataType 等）。
            rows：全量数据行。

        返回：包含数据集 ID、列信息、预览行、行数、存储类型等元信息的字典。
        副作用：在磁盘写入 CSV 文件，并在数据库中新增 ResultSetModel 记录。
        """
        if len(rows) > self.settings.analysis_dataset_max_rows:
            raise ValueError(f"分析数据集不能超过 {self.settings.analysis_dataset_max_rows} 行")
        dataset_id = new_id("result")
        file_path = self.settings.analysis_dataset_dir / f"{dataset_id}.csv"
        # 全量行在独立线程中落盘，避免阻塞事件循环
        await asyncio.to_thread(_write_csv_atomic, file_path, columns, rows)
        # 单文件磁盘配额校验，超限则删除文件并报错，避免占用过多空间
        maximum_bytes = self.settings.analysis_dataset_max_disk_mb * 1024 * 1024
        if file_path.stat().st_size > maximum_bytes:
            file_path.unlink(missing_ok=True)
            raise ValueError(f"单个分析数据集超过 {self.settings.analysis_dataset_max_disk_mb} MB 磁盘限制")
        # 数据集过期时间 = 当前 UTC + 配置的存活时长
        expires_at = utc_now() + timedelta(hours=self.settings.analysis_dataset_ttl_hours)
        safe_columns = _json_safe(columns)
        # 仅取前 N 行作为预览存入数据库
        preview = _json_safe(rows[: self.settings.analysis_dataset_preview_rows])
        async with session_factory() as session:
            model = ResultSetModel(
                id=dataset_id,
                run_id=run_id,
                columns=safe_columns,
                rows=preview,
                total_rows=len(rows),
                # 预览行少于总行数说明数据库只保存了部分数据（完整数据在 CSV）
                truncated=len(preview) < len(rows),
                storage_type="csv",
                file_path=str(file_path),
                expires_at=expires_at,
            )
            session.add(model)
            # 提交失败需回滚并清理已落盘文件，保证数据库与磁盘状态一致
            try:
                await session.commit()
            except Exception:
                file_path.unlink(missing_ok=True)
                raise
        # 每次写入后顺带触发一次清理，维持磁盘配额
        await self.cleanup()
        return {
            "id": dataset_id,
            "columns": safe_columns,
            "previewRows": preview,
            "rowCount": len(rows),
            "truncated": len(preview) < len(rows),
            "storageType": "csv",
            "filePath": str(file_path),
            "sizeBytes": file_path.stat().st_size,
            "expiresAt": expires_at.isoformat(),
        }

    async def read_rows(self, result_set: ResultSetModel, *, offset: int, limit: int) -> list[dict[str, Any]]:
        """按分页读取数据集行。

        若存储类型不是 CSV（已退化为 SQLite）或文件缺失，则直接返回 SQLite 中的预览行；
        否则从 CSV 文件分页读取完整数据。
        """
        if result_set.storage_type != "csv" or not result_set.file_path:
            return result_set.rows[offset : offset + limit]
        path = Path(result_set.file_path)
        if not path.exists():
            # 文件已过期被清理时，退化为使用 SQLite 预览
            return result_set.rows[offset : offset + limit]
        return await asyncio.to_thread(_read_csv_rows, path, result_set.columns, offset, limit)

    async def cleanup(self) -> int:
        """清理过期或超出磁盘配额的数据集。

        策略：先删除所有已过期的数据集；若仍超配额，则按创建时间从最旧开始删除，
        直到满足磁盘上限。被删除的文件行仅保留在 SQLite 预览中（storage_type 置为 sqlite）。

        返回：本次清理移除的数据集数量。
        """
        async with session_factory() as session:
            statement = (
                select(ResultSetModel)
                .where(ResultSetModel.storage_type == "csv")
                .order_by(ResultSetModel.created_at.asc())
            )
            datasets = list((await session.scalars(statement)).all())
            now = utc_now()
            # 第一步：标记所有已过期的数据集为待移除
            remove = {item.id for item in datasets if item.expires_at and _aware(item.expires_at) <= now}
            active = [item for item in datasets if item.id not in remove]
            maximum = self.settings.analysis_dataset_max_disk_mb * 1024 * 1024
            # 第二步：按创建时间从旧到新累加活跃数据集大小，超出配额则继续移除
            total = sum(_file_size(item.file_path) for item in active)
            for item in active:
                if total <= maximum:
                    break
                size = _file_size(item.file_path)
                remove.add(item.id)
                total -= size
            removed = [item for item in datasets if item.id in remove]
            removed_paths = [Path(item.file_path) for item in removed if item.file_path]
            # 被移除文件的数据集退化为仅在 SQLite 保留预览
            for item in removed:
                item.storage_type = "sqlite"
                item.file_path = None
                item.expires_at = None
                item.truncated = item.total_rows > len(item.rows)
            if removed:
                await session.commit()
        # 数据库变更提交后再删除磁盘文件，避免先删文件导致状态不一致
        for path in removed_paths:
            path.unlink(missing_ok=True)
        return len(removed)

    async def delete_files(self, file_paths: list[str]) -> int:
        """删除数据库记录已移除的数据集文件。

        只允许删除 ``analysis_dataset_dir`` 根目录下、由本服务命名的
        ``result_*.csv``，避免受污染的数据库路径导致越界删除。
        文件已不存在视为幂等成功，但会记录告警以便排查存储漂移。
        """
        owned_paths = [self._owned_csv_path(value) for value in dict.fromkeys(file_paths) if value]
        return await asyncio.to_thread(self._delete_owned_files, owned_paths)

    async def cleanup_orphans(self) -> int:
        """删除数据集目录中没有 ``result_sets`` 记录引用的孤儿 CSV。"""
        async with session_factory() as session:
            statement = select(ResultSetModel.file_path).where(ResultSetModel.file_path.is_not(None))
            referenced_values = list((await session.scalars(statement)).all())
        referenced = {
            self._owned_csv_path(value)
            for value in referenced_values
            if value and self._is_owned_csv_path(value)
        }
        root = self.settings.analysis_dataset_dir.resolve()
        orphaned = [path.resolve() for path in root.glob("result_*.csv") if path.resolve() not in referenced]
        return await asyncio.to_thread(self._delete_owned_files, orphaned)

    def _is_owned_csv_path(self, value: str) -> bool:
        try:
            self._owned_csv_path(value)
        except ValueError:
            return False
        return True

    def _owned_csv_path(self, value: str) -> Path:
        root = self.settings.analysis_dataset_dir.resolve()
        path = Path(value).resolve()
        if path.parent != root or path.suffix.lower() != ".csv" or not path.name.startswith("result_"):
            raise ValueError(f"数据集文件不属于受管目录: {value}")
        return path

    @staticmethod
    def _delete_owned_files(paths: list[Path]) -> int:
        removed = 0
        for path in paths:
            if not path.exists():
                logger.warning("dataset file already missing: path=%s", path)
                continue
            path.unlink()
            removed += 1
        return removed


def _write_csv_atomic(path: Path, columns: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    """原子写入 CSV：先写临时文件，再 rename 替换目标，避免半写文件被读到。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    fieldnames = [str(column.get("name")) for column in columns]
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: _csv_value(row.get(name)) for name in fieldnames})
    # os.replace 在同一文件系统上是原子操作，读者不会看到中间状态
    os.replace(temporary, path)


def _read_csv_rows(
    path: Path, columns: list[dict[str, Any]], offset: int, limit: int
) -> list[dict[str, Any]]:
    """从 CSV 分页读取并按列元信息做类型还原。"""
    # 依据列定义建立字段名 -> 目标类型映射，用于把字符串还原为对应类型
    types = {str(column.get("name")): str(column.get("dataType") or "string") for column in columns}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {key: _typed_value(value, types.get(key, "string")) for key, value in row.items()}
            for row in islice(reader, offset, offset + limit)
        ]


def _csv_value(value: Any) -> Any:
    """将单个值转换为 CSV 可写形式（日期/时间转为 ISO 字符串，None 转空串）。"""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _typed_value(value: str, data_type: str) -> Any:
    """按声明类型把 CSV 字符串还原为 Python 原生值；转换失败或空串时回退原值/None。"""
    if value == "":
        return None
    normalized = data_type.lower()
    try:
        if normalized in {"integer", "int", "bigint"}:
            return int(value)
        if normalized in {"number", "float", "double", "decimal"}:
            return float(value)
        if normalized == "boolean":
            return value.lower() in {"true", "1"}
    except ValueError:
        return value
    return value


def _file_size(file_path: str | None) -> int:
    """安全获取文件字节数，文件缺失/不可访问时返回 0。"""
    if not file_path:
        return 0
    try:
        return Path(file_path).stat().st_size
    except OSError:
        return 0


def _json_safe(value: Any) -> Any:
    """Convert database-native values into lossless JSON-compatible values."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _aware(value):
    """把无时区信息的时间补全为与服务器一致的 UTC 时区，便于过期比较。"""
    return value if value.tzinfo else value.replace(tzinfo=utc_now().tzinfo)
