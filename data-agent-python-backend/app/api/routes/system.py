"""系统级路由：启动引导、健康检查、智能体/数据源列举与数据源连通性测试。

这些端点不依赖具体会话/运行，主要服务前端首屏初始化与运维健康探测。
当前智能体与数据源为内置单例配置，后续可扩展为可配置的多实例。
"""

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
from app.config import get_settings


router = APIRouter(tags=["system"])


def agents() -> list[AgentProfile]:
    """返回当前可用的智能体清单（目前为内置默认智能体）。"""
    return [
        AgentProfile(
            id="default-analysis",
            name="通用数据分析",
            description="支持自然语言查询、SQL 分析和结果解释",
            is_default=True,
        )
    ]


def datasources() -> list[DatasourceSummary]:
    """返回当前已配置的数据源清单（目前为内置 sales-db）。"""
    return [
        DatasourceSummary(id="sales-db", name="销售分析数据库", type="mysql", status="configured", is_default=True)
    ]


@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap() -> BootstrapResponse:
    """首屏引导接口：聚合默认智能体、推荐问题、数据源与功能开关。"""
    settings = get_settings()
    return BootstrapResponse(
        default_agent_id="default-analysis",
        agents=agents(),
        recommended_questions=["分析最近30天销量变化", "找出复购率最高的用户群", "哪些商品出现异常波动"],
        datasources=datasources(),
        features={
            "humanReview": True,
            "charts": True,
            "exports": True,
            # Python 分析开关由配置决定
            "pythonAnalysis": settings.python_analysis_enabled,
            "multiAgent": False,
            "skills": False,
        },
    )


@router.get("/health", response_model=HealthResponse)
async def health(session: SessionDependency) -> HealthResponse:
    # 用一条轻量 SQL 验证数据库可达
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
    """测试指定数据源连通性，返回连接状态与延迟；非内置数据源视为不存在。"""
    if datasource_id != "sales-db":
        raise ResourceNotFoundError("datasource", datasource_id)
    from app.application.executor import graph_runtime

    started = monotonic()
    try:
        # 通过图运行时读取库表元数据，既能验证连接又能统计表数量
        snapshot = await graph_runtime.database.schema_snapshot()
        table_count = len(snapshot.get("tables", []))
        return DatasourceTestResponse(
            datasource_id=datasource_id,
            status="connected",
            latency_ms=int((monotonic() - started) * 1000),
            message=f"连接成功，读取到 {table_count} 张表",
        )
    except Exception as error:
        # 连接失败也返回 200，由响应体 status= failed 表达异常，便于前端统一处理
        return DatasourceTestResponse(
            datasource_id=datasource_id,
            status="failed",
            latency_ms=int((monotonic() - started) * 1000),
            message=str(error),
        )
