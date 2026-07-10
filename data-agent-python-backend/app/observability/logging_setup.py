"""集中式日志配置与日志辅助函数。

本模块解决两类问题：

1. 在 FastAPI 启动时统一配置根日志记录器，确保 INFO 级别日志（尤其是
   模型输入/输出、工具调用）能够被控制台看到，而不是被 Python 默认的
   ``lastResort`` handler 吞掉或只输出 WARNING 以上级别。
2. 提供 ``truncate_text`` 等辅助函数，避免把超长的提示词、模型返回或工具
   结果直接写进日志造成刷屏。

所有业务模块都通过 ``logging.getLogger(__name__)`` 获取自己的 logger，
最终由这里统一把日志输出到控制台和可选的本地日志文件。
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


# 默认日志格式：时间 + 级别 + 产生日志的模块名 + 消息。
# 模型输入/输出与工具调用的关键字段（runId、name 等）已经写在消息体里，
# 因此格式保持简洁即可。
DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(
    level: int = logging.INFO,
    fmt: str = DEFAULT_FORMAT,
    *,
    file_path: str | Path | None = None,
    file_max_bytes: int = 20 * 1024 * 1024,
    file_backup_count: int = 5,
) -> None:
    """配置根日志记录器，使其输出结构化日志。

    幂等：保留 uvicorn 等框架已安装的控制台 handler，并只在缺失时补充
    控制台或文件 handler，避免重复输出。

    Args:
        level: 根日志级别，默认 ``logging.INFO``。
        fmt: 日志行格式字符串。
        file_path: 日志文件路径；为空时不写文件。
        file_max_bytes: 单个日志文件最大字节数。
        file_backup_count: 轮转保留文件数量。
    """
    root = logging.getLogger()
    formatter = logging.Formatter(fmt)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    if file_path is not None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        resolved = path.resolve()
        has_same_file = any(
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename).resolve() == resolved
            for handler in root.handlers
        )
        if not has_same_file:
            file_handler = RotatingFileHandler(
                resolved,
                maxBytes=file_max_bytes,
                backupCount=file_backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
    root.setLevel(level)


def truncate_text(text: str, max_chars: int) -> str:
    """将文本截断到 ``max_chars`` 个字符，超出部分用省略提示标注。

    用于把可能很长的模型提示词、模型返回内容、工具结果等内容安全地写进日志，
    既保留排查所需的信息，又避免单次日志过大。

    Args:
        text: 待截断文本。
        max_chars: 允许的最大字符数；小于等于 0 表示不截断。

    Returns:
        截断后的文本；若被截断会在末尾追加 ``…(已省略 N 字符)``。
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return text[:max_chars] + f"…(已省略 {omitted} 字符)"
