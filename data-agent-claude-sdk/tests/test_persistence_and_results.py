import pytest

from app.domain.errors import ResourceNotFoundError
from app.domain.models import QueryResult, TenantContext
from app.infrastructure.persistence.database import ControlDatabase
from app.infrastructure.results.store import ResultStore


@pytest.mark.asyncio
async def test_result_is_persisted_and_tenant_scoped(tmp_path):
    database = ControlDatabase(f"sqlite+aiosqlite:///{tmp_path / 'control.db'}")
    await database.initialize()
    context = TenantContext("tenant-a", "user-a", "conversation-a", "run-a")
    await database.create_conversation(context)
    await database.create_run(context, "test")
    store = ResultStore(tmp_path / "results")
    result_id, path = await store.save(
        context,
        QueryResult(["id", "amount"], [{"id": 1, "amount": 10}], 1, False),
    )
    await database.save_result_set(context, result_id, str(path), ["id", "amount"], 1, False, "ok", {"status": "passed"})
    # 模拟升级：旧版本只有 result_sets，重新初始化时应自动补成 SQL 产物。
    await database.initialize()

    metadata = await database.get_result_set(context, result_id)
    page = await store.read(metadata["file_path"], offset=0, limit=50)

    assert page["rows"] == [{"id": 1, "amount": 10}]
    async with database.connect() as connection:
        cursor = await connection.execute("SELECT kind, file_path FROM artifacts WHERE id=?", (result_id,))
        artifact = await cursor.fetchone()
    assert artifact[0] == "sql_result"
    assert artifact[1] == str(path)
    assert path.with_suffix(".csv").read_text(encoding="utf-8-sig").splitlines() == ["id,amount", "1,10"]
    with pytest.raises(ResourceNotFoundError):
        await database.get_result_set(
            TenantContext("tenant-b", "user-b", "conversation-a", "run-a"),
            result_id,
        )
