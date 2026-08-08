"""记忆（memory）模块的公共出口。

集中导出记忆体系对外暴露的核心组件，供上层会话编排（context / workflow）复用：
- ContextBuilder：根据持久化消息与已召回记忆组装受限的模型上下文。
- ConversationSummarizer：在上下文预算吃紧时，将历史对话压缩为持久摘要。
- CoreMemoryService：跨会话的用户长期记忆（profile）改写服务。
- LongTermMemoryExtractor：借助 LLM 抽取长期记忆候选并按确定性策略落库。
- MemoryProvider：在 SQLite（事实来源）之外维护向量检索索引。

设计要点：SQLite 始终是唯一事实来源（source of truth），Chroma 仅作为可选的
检索加速层；当未配置 chroma 后端时，相关检索自动退化为基于词元的词汇匹配。
"""

from app.memory.context import ContextBuilder
from app.memory.core import CoreMemoryService
from app.memory.extractor import LongTermMemoryExtractor
from app.memory.provider import MemoryProvider
from app.memory.summary import ConversationSummarizer

__all__ = [
    "ContextBuilder",
    "ConversationSummarizer",
    "CoreMemoryService",
    "LongTermMemoryExtractor",
    "MemoryProvider",
]
