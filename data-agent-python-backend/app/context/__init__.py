"""上下文管理：控制送给大模型的上下文规模。

提供 token 估算与截断能力，以及基于消息列表的上下文压缩（compaction）。
本包对外仅暴露最常用的人口（estimate_tokens / truncate_to_tokens）。
"""

from app.context.tokens import estimate_tokens, truncate_to_tokens

__all__ = ["estimate_tokens", "truncate_to_tokens"]
