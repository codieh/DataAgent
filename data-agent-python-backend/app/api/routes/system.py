from datetime import datetime, timezone
from time import monotonic

from fastapi import APIRouter
from sqlalchemy import text

from app.api.dependencies import SessionDependency
from app.api.schemas import (
    AgentProfile,
    BootstrapResponse,
    DatasourceSummary,
    DatasourceTestResponse,
    HealthResponse,
)
from app.domain.errors import ResourceNotFoundError


router = APIRouter(tags=["system"])


def agents() -> list[AgentProfile]:
    return [
        AgentProfile(
            id="default-analysis",
            name="通用数据分析",
            description="支持自然语言查询、SQL 分析和结果解释",
            is_default=True,
        )
    ]


def datasources() -> list[DatasourceSummary]:
    return [
        DatasourceSummary(id="sales-db", name="销售分析数据库", type="mysql", status="configured", is_default=True)
    ]


@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap() -> BootstrapResponse:
    return BootstrapResponse(
        default_agent_id="default-analysis",
        agents=agents(),
        recommended_questions=["分析最近30天销量变化", "找出复购率最高的用户群", "哪些商品出现异常波动"],
        datasources=datasources(),
        features={
            "humanReview": True,
            "charts": True,
            "exports": True,
            "pythonAnalysis": False,
            "multiAgent": False,
            "skills": False,
        },
    )


@router.get("/health", response_model=HealthResponse)
async def health(session: SessionDependency) -> HealthResponse:
    await session.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="connected", version="0.2.0", timestamp=datetime.now(timezone.utc))


@router.get("/agents", response_model=list[AgentProfile])
async def list_agents() -> list[AgentProfile]:
    return agents()


@router.get("/datasources", response_model=list[DatasourceSummary])
async def list_datasources() -> list[DatasourceSummary]:
    return datasources()


@router.post("/datasources/{datasource_id}/test", response_model=DatasourceTestResponse)
async def test_datasource(datasource_id: str) -> DatasourceTestResponse:
    if datasource_id != "sales-db":
        raise ResourceNotFoundError("datasource", datasource_id)
    from app.application.executor import graph_runtime

    started = monotonic()
    try:
        snapshot = await graph_runtime.database.schema_snapshot()
        table_count = len(snapshot.get("tables", []))
        return DatasourceTestResponse(
            datasource_id=datasource_id,
            status="connected",
            latency_ms=int((monotonic() - started) * 1000),
            message=f"连接成功，读取到 {table_count} 张表",
        )
    except Exception as error:
        return DatasourceTestResponse(
            datasource_id=datasource_id,
            status="failed",
            latency_ms=int((monotonic() - started) * 1000),
            message=str(error),
        )
