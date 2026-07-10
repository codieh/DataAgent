"""结果相关路由：产物查看、结果集分页/导出、运行整体导出。

提供两种导出形态：结果集维度（CSV/XLSX，优先直接回传已落盘的 CSV 全量文件）
与运行维度（Markdown/CSV/XLSX，聚合分析摘要与结果集数据）。导出受限条件包括
分页上限、已过期截断等，相关规则在接口内做校验。
"""

import csv
import io
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.api.dependencies import SessionDependency
from app.api.presenters import artifact_response
from app.api.schemas import ArtifactResponse, ResultSetResponse
from app.application import RunViewService
from app.config import get_settings
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.repository import Repository
from app.analysis import AnalysisDatasetStore


router = APIRouter(tags=["results"])


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(artifact_id: str, session: SessionDependency) -> ArtifactResponse:
    return artifact_response(await RunViewService(session).artifact(artifact_id))


@router.get("/result-sets/{result_set_id}", response_model=ResultSetResponse)
async def get_result_set(
    result_set_id: str,
    session: SessionDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1),
) -> ResultSetResponse:
    settings = get_settings()
    if page_size > settings.result_page_size_max:
        from app.domain.errors import InvalidOperationError

        raise InvalidOperationError(f"page_size must be <= {settings.result_page_size_max}")
    result_set = await Repository(session).get_result_set(result_set_id)
    if not result_set:
        raise ResourceNotFoundError("result_set", result_set_id)
    # 偏移量换算：页码从 1 开始
    start = (page - 1) * page_size
    rows = await AnalysisDatasetStore(settings).read_rows(result_set, offset=start, limit=page_size)
    return ResultSetResponse(
        id=result_set.id,
        columns=result_set.columns,
        rows=rows,
        page=page,
        page_size=page_size,
        returned_rows=len(rows),
        total_rows=result_set.total_rows,
        # CSV 落盘的结果集即使 SQLite 只存预览，仍可完整分页；只有 SQLite-only 时才真正截断
        truncated=result_set.truncated and result_set.storage_type != "csv",
    )


@router.get("/result-sets/{result_set_id}/export")
async def export_result_set(
    result_set_id: str,
    session: SessionDependency,
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
):
    result_set = await Repository(session).get_result_set(result_set_id)
    if not result_set:
        raise ResourceNotFoundError("result_set", result_set_id)
    # CSV 且文件仍在磁盘时，直接回传原始文件，避免重复读库重建
    if format == "csv" and result_set.storage_type == "csv" and result_set.file_path:
        path = Path(result_set.file_path)
        if path.exists():
            return FileResponse(
                path,
                media_type="text/csv; charset=utf-8",
                filename=f"{result_set_id}.csv",
            )
    rows = await AnalysisDatasetStore(get_settings()).read_rows(
        result_set, offset=0, limit=result_set.total_rows
    )
    # 文件已过期、仅剩预览时不允许导出原始数据
    if result_set.truncated and len(rows) < result_set.total_rows:
        from app.domain.errors import InvalidOperationError

        raise InvalidOperationError("完整结果文件已过期，当前仅保留预览，无法导出原始数据。")
    columns = result_set.columns
    if format == "xlsx":
        return _xlsx_response(result_set_id, columns, rows)
    return _csv_response(result_set_id, columns, rows)


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: str,
    session: SessionDependency,
    format: str = Query(pattern="^(csv|markdown|xlsx)$"),
) -> StreamingResponse:
    repository = Repository(session)
    run = await repository.get_run(run_id)
    if not run:
        raise ResourceNotFoundError("run", run_id)
    queries = await repository.list_queries(run_id)
    artifacts = await repository.list_artifacts(run_id)
    # 取分析类型产物的 payload 作为摘要来源（不存在则空字典）
    analysis = next((item.payload for item in artifacts if item.type == "analysis"), {})
    if format == "markdown":
        content = f"# {analysis.get('title', run.question)}\n\n{analysis.get('summary', '')}\n"
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{run_id}.md"'},
        )
    rows: list[dict] = []
    columns: list[dict] = []
    # 以最后一次查询关联的结果集作为导出数据来源
    if queries and queries[-1].result_set_id:
        result_set = await repository.get_result_set(queries[-1].result_set_id)
        if result_set:
            rows = await AnalysisDatasetStore(get_settings()).read_rows(
                result_set, offset=0, limit=result_set.total_rows
            )
            columns = result_set.columns
    if format == "xlsx":
        return _xlsx_response(run_id, columns, rows)
    # CSV 导出附带 BOM，保证 Excel 正确识别 UTF-8
    return _csv_response(run_id, columns, rows, with_bom=True)


def _xlsx_response(name: str, columns: list[dict], rows: list[dict]) -> StreamingResponse:
    """把列与行渲染为 XLSX 文件并以流式响应返回。"""
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "结果"
    fieldnames = [column["name"] for column in columns]
    if fieldnames:
        sheet.append(fieldnames)
        for row in rows:
            sheet.append([row.get(field) for field in fieldnames])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
    )


def _csv_response(
    name: str, columns: list[dict], rows: list[dict], *, with_bom: bool = False
) -> StreamingResponse:
    """把列与行渲染为 CSV 流式响应；``with_bom`` 为 True 时加 UTF-8 BOM 以兼容 Excel。"""
    output = io.StringIO()
    fieldnames = [column["name"] for column in columns]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    if fieldnames:
        writer.writeheader()
        writer.writerows(rows)
    encoding = "utf-8-sig" if with_bom else "utf-8"
    return StreamingResponse(
        iter([output.getvalue().encode(encoding)]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )
