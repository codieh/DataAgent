"""轻量确定性检索服务。

Schema 检索直接使用实时数据库快照；业务文档先以 Markdown/TXT 文件读取，后续
可以在不改变 Tool 协议的情况下替换为预先构建的向量索引。
"""

import re
from pathlib import Path
from typing import Any


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[\w\u4e00-\u9fff]+", value) if len(token) > 1}


class SchemaSearchService:
    def search(self, query: str, schema: dict[str, Any], *, limit: int = 8) -> dict[str, Any]:
        query_tokens = _tokens(query)
        scored: list[tuple[int, dict[str, Any], list[str]]] = []
        for table in schema.get("tables", []):
            text = " ".join(
                [
                    str(table.get("name", "")),
                    str(table.get("comment", "")),
                    " ".join(str(column.get("name", "")) for column in table.get("columns", [])),
                    " ".join(str(column.get("comment", "")) for column in table.get("columns", [])),
                ]
            )
            matched = sorted(query_tokens & _tokens(text))
            score = len(matched)
            if score or not query_tokens:
                scored.append((score, table, matched))
        scored.sort(key=lambda item: (-item[0], str(item[1].get("name", ""))))
        selected = scored[:limit]
        return {
            "tables": [item[1] for item in selected],
            "reasons": {str(item[1].get("name")): item[2] for item in selected},
        }


class KnowledgeSearchService:
    def __init__(self, root: Path):
        self.root = root

    def search(self, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        hits: list[tuple[int, Path, str]] = []
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in {".md", ".markdown", ".txt"} or not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            score = len(query_tokens & _tokens(content))
            if score:
                snippet = content[:1500]
                hits.append((score, path, snippet))
        hits.sort(key=lambda item: (-item[0], str(item[1])))
        return [
            {"source": str(path.relative_to(self.root)), "score": score, "snippet": snippet}
            for score, path, snippet in hits[:limit]
        ]
