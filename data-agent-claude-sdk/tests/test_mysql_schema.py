from app.infrastructure.datasource.mysql import BusinessDatabase


class FakeCursor:
    def __init__(self):
        self.last_query = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query: str, _params=None):
        self.last_query = query

    def fetchall(self):
        if "information_schema.tables" in self.last_query:
            return [{"table_name": "orders", "table_comment": "订单表"}]
        if "information_schema.columns" in self.last_query:
            return [{
                "column_name": "id",
                "data_type": "bigint",
                "column_type": "bigint",
                "column_comment": "主键",
                "is_nullable": "NO",
            }]
        return []


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        return None


def test_schema_snapshot_keeps_table_name_before_renaming(monkeypatch):
    database = BusinessDatabase("mysql://readonly:password@127.0.0.1:3306/product_db")
    monkeypatch.setattr(database, "_connect", lambda _tenant_id: FakeConnection())

    snapshot = database._schema_snapshot_sync("local-tenant")

    assert snapshot["tables"] == [{
        "name": "orders",
        "comment": "订单表",
        "columns": [{
            "name": "id",
            "data_type": "bigint",
            "column_type": "bigint",
            "comment": "主键",
            "nullable": False,
        }],
        "foreign_keys": [],
    }]
