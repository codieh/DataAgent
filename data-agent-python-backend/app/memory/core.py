"""核心长期记忆（Core Memory）改写服务。

职责：将用户跨会话的「紧凑记忆文档」作为单一可改写对象，借助 LLM 根据用户指令
与最新消息进行更新；更新前执行安全与预算约束。

设计要点：
- SQLite（repository.save_core_memory）为唯一事实来源。
- 拒绝保存敏感凭据：通过正则 _SENSITIVE 检测密码 / 密钥 / 访问令牌。
- 限制记忆长度（core_memory_max_tokens），避免无限膨胀。
- 仅当内容确有变化时才落库，减少无谓写入。
"""

import json
import re
from typing import Any

from app.config import Settings
from app.context import estimate_tokens
from app.workflow.outputs import CoreMemoryRewriteOutput
from app.workflow.ports import LlmClient
from app.workflow.prompts import CORE_MEMORY_REWRITE_SYSTEM


# 敏感凭据正则：匹配「key/密码/密钥 = 值」形式，以及 sk- 开头的 API Key
_SENSITIVE = re.compile(
    r"(?i)(api[_ -]?key|access[_ -]?token|password|密码|密钥)\s*[:=]\s*\S+|sk-[A-Za-z0-9_-]{12,}"
)


class CoreMemoryService:
    """将用户跨会话的紧凑长期记忆作为单篇文档进行改写。"""

    def __init__(self, settings: Settings, llm: LlmClient):
        """初始化核心记忆服务。

        Args:
            settings: 全局配置（含记忆 token 上限）。
            llm: LLM 客户端，用于按指令改写记忆。
        """
        self.settings = settings
        self.llm = llm

    async def rewrite(
        self,
        *,
        repository: Any,
        instruction: str,
        user_message: str,
        profile_id: str = "default",
    ) -> dict[str, Any]:
        """按用户指令重写核心长期记忆。

        Args:
            repository: 持久化仓储，读取 / 保存记忆。
            instruction: 用户给出的记忆修改要求。
            user_message: 触发本次改写的用户最新消息（作为上下文）。
            profile_id: 记忆归属的 profile 标识，默认 "default"。

        Returns:
            {"changed": 是否实际落库, "memory": 记忆内容, "summary": 改写摘要}。

        Raises:
            ValueError: 指令为空、写入内容含敏感凭据或超出 token 上限时抛出。
        """
        instruction = instruction.strip()
        if not instruction:
            raise ValueError("长期记忆修改要求不能为空")
        current = await repository.get_core_memory(profile_id)
        current_content = current.content if current is not None else ""
        # 将现有记忆、用户消息与改写指令一并交给 LLM，得到结构化改写结果
        result = await self.llm.complete_model(
            CoreMemoryRewriteOutput,
            CORE_MEMORY_REWRITE_SYSTEM,
            json.dumps(
                {
                    "currentMemory": current_content,
                    "userMessage": user_message,
                    "instruction": instruction,
                },
                ensure_ascii=False,
            ),
        )
        updated = result.content.strip()
        # 安全护栏：禁止把密码 / 密钥 / 访问令牌写进长期记忆
        if _SENSITIVE.search(updated):
            raise ValueError("长期记忆不能保存密码、密钥或访问令牌")
        if estimate_tokens(updated) > self.settings.core_memory_max_tokens:
            raise ValueError(f"长期记忆不能超过 {self.settings.core_memory_max_tokens} tokens")
        # 仅当内容确有明显变化时才落库，避免无效写入
        changed = bool(result.changed and updated != current_content.strip())
        if changed:
            await repository.save_core_memory(updated, profile_id)
        return {"changed": changed, "memory": updated or current_content, "summary": result.summary}
