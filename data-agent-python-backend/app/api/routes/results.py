import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import SessionDependency
from app.api.presenters import artifact_response
from app.api.schemas import ArtifactResponse, ResultSetResponse
from app.application import RunViewService
from app.config import get_settings
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.repository import Repository


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
    start = (page - 1) * page_size
    rows = result_set.rows[start : start + page_size]
    return ResultSetResponse(
        id=result_set.id,
        columns=result_set.columns,
        rows=rows,
        page=page,
        page_size=page_size,
        returned_rows=len(rows),
        total_rows=result_set.total_rows,
        truncated=result_set.truncated,
    )


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: str,
    session: SessionDependency,
    format: str = Query(pattern="^(csv|markdown)$"),
) -> StreamingResponse:
    repository = Repository(session)
    run = await repository.get_run(run_id)
    if not run:
        raise ResourceNotFoundError("run", run_id)
    queries = await repository.list_queries(run_id)
    artifacts = await repository.list_artifacts(run_id)
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
    if queries and queries[-1].result_set_id:
        result_set = await repository.get_result_set(queries[-1].result_set_id)
        if result_set:
            rows, columns = result_set.rows, result_set.columns
    output = io.StringIO()
    fieldnames = [column["name"] for column in columns]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    if fieldnames:
        writer.writeheader()
        writer.writerows(rows)
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'},
    )

