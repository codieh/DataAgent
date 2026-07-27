"""对话聚合仓储（Conversation repository）。

负责对话、消息、用户核心记忆、对话/长期记忆条目、摘要状态等实体的持久化与查询。
除常规 CRUD 外，还维护 SQLite 下的 FTS5 全文索引（``conversation_history_fts``），
并在记忆条目上实现基于 TTL 与重要度的保留/淘汰策略（``enforce_memory_retention``）。

说明：涉及 FTS 的写入仅在 SQLite 后端生效，且依赖 ``self.session.bind.dialect``
为 sqlite；非 SQLite 时相关分支直接跳过。
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import and_, delete, or_, select, text

from app.infrastructure.persistence.models import (
    AnalysisRunModel,
    ConversationModel,
    ConversationSummaryStateModel,
    MemoryItemModel,
    MessageModel,
    UserCoreMemoryModel,
    utc_now,
)
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class ConversationRepository(RepositoryBase):
    """对话聚合的仓储实现：管理对话及其派生数据。"""

    async def create_conversation(self, *, title: str, agent_id: str, datasource_id: str) -> ConversationModel:
        conversation = ConversationModel(
            id=new_id("conv"), title=title, agent_id=agent_id, datasource_id=datasource_id
        )
        self.session.add(conversation)
        # 若存在用户核心记忆，则作为 system 消息注入新对话，提供用户画像上下文。
        core_memory = await self.session.get(UserCoreMemoryModel, "default")
        if core_memory is not None and core_memory.content.strip():
            self.session.add(
                MessageModel(
                    id=new_id("msg"),
                    conversation_id=conversation.id,
                    run_id=None,
                    role="system",
                    content=(
                        "用户长期记忆：\n"
                        f"{core_memory.content.strip()}\n"
                    ),
                    content_type="system",
                )
            )
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_core_memory(self, profile_id: str = "default") -> UserCoreMemoryModel | None:
        """按 profile_id 获取用户核心记忆（默认 ``"default"``）。"""
        return await self.session.get(UserCoreMemoryModel, profile_id)

    async def save_core_memory(self, content: str, profile_id: str = "default") -> UserCoreMemoryModel:
        """保存（新建或覆盖）用户核心记忆文本。"""
        memory = await self.get_core_memory(profile_id)
        if memory is None:
            memory = UserCoreMemoryModel(profile_id=profile_id, content=content.strip())
            self.session.add(memory)
        else:
            memory.content = content.strip()
            memory.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def get_conversation(self, conversation_id: str) -> ConversationModel | None:
        """按 ID 获取对话。"""
        return await self.session.get(ConversationModel, conversation_id)

    async def list_conversations(self, query: str | None, limit: int) -> list[ConversationModel]:
        """列出对话，按更新时间倒序；``query`` 非空时按标题模糊匹配。"""
        statement = select(ConversationModel).order_by(ConversationModel.updated_at.desc()).limit(limit)
        if query:
            statement = statement.where(ConversationModel.title.ilike(f"%{query.strip()}%"))
        return list((await self.session.scalars(statement)).all())

    async def update_conversation(self, conversation: ConversationModel, **changes: Any) -> ConversationModel:
        """按传入字段更新对话；标题变更时同步维护 SQLite 全文索引中的标题。

        ``changes`` 中值为 ``None`` 的字段被忽略，避免误清空；标题更新后需同步
        改写 ``conversation_history_fts`` 中的 ``title``（仅 SQLite）。
        """
        for key, value in changes.items():
            if value is not None:
                setattr(conversation, key, value)
        conversation.updated_at = utc_now()
        if "title" in changes and changes.get("title") and self.session.bind and self.session.bind.dialect.name == "sqlite":
            # 同步更新全文索引中的标题，保证搜索结果标题一致
            await self.session.execute(
                text("UPDATE conversation_history_fts SET title = :title WHERE conversation_id = :conversation_id"),
                {"title": changes["title"], "conversation_id": conversation.id},
            )
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def delete_conversation(self, conversation_id: str) -> bool:
        """删除对话；SQLite 下先清理其全文索引，再删主表记录。

        返回是否实际删除了记录（依赖 ``rowcount``）。FS的索引需手动清理，
        因为 FTS 虚拟表不支持外键级联删除。
        """
        if self.session.bind and self.session.bind.dialect.name == "sqlite":
            # FTS 虚拟表不支持外键级联，需手动删除相关索引行
            await self.session.execute(
                text("DELETE FROM result_history_fts WHERE conversation_id = :conversation_id"),
                {"conversation_id": conversation_id},
            )
            await self.session.execute(
                text("DELETE FROM conversation_history_fts WHERE conversation_id = :conversation_id"),
                {"conversation_id": conversation_id},
            )
        result = await self.session.execute(delete(ConversationModel).where(ConversationModel.id == conversation_id))
        await self.session.commit()
        return bool(result.rowcount)

    async def add_message(
        self, *, conversation_id: str, run_id: str | None, role: str, content: str
    ) -> MessageModel:
        """新增一条消息；若是 user/assistant 且为 SQLite，则同步写入全文索引。"""
        message = MessageModel(
            id=new_id("msg"), conversation_id=conversation_id, run_id=run_id, role=role, content=content
        )
        self.session.add(message)
        # 仅 user/assistant 消息进入搜索索引；需先取对话标题一并写入 FTS
        if role in {"user", "assistant"} and self.session.bind and self.session.bind.dialect.name == "sqlite":
            conversation = await self.get_conversation(conversation_id)
            await self.session.execute(
                text("""INSERT INTO conversation_history_fts
                (message_id, conversation_id, role, title, content)
                VALUES (:message_id, :conversation_id, :role, :title, :content)"""),
                {
                    "message_id": message.id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "title": conversation.title if conversation else "",
                    "content": content,
                },
            )
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def list_messages(self, conversation_id: str) -> list[MessageModel]:
        """列出某对话的真实消息，按创建时间升序。

        旧版本曾为执行重试重复写入用户消息。原始记录继续保留用于审计，但不再
        投影到会话历史，避免旧数据继续影响前端展示和 Agent 上下文。
        """
        retry_run_ids = select(AnalysisRunModel.id).where(
            AnalysisRunModel.retry_of_run_id.is_not(None)
        )
        statement = (
            select(MessageModel)
            .where(
                MessageModel.conversation_id == conversation_id,
                or_(
                    MessageModel.role != "user",
                    MessageModel.run_id.is_(None),
                    MessageModel.run_id.not_in(retry_run_ids),
                ),
            )
            .order_by(MessageModel.created_at.asc())
        )
        return list((await self.session.scalars(statement)).all())

    async def get_user_message_for_run(self, run_id: str) -> MessageModel | None:
        """获取某运行对应的用户提问消息。"""
        statement = select(MessageModel).where(MessageModel.run_id == run_id, MessageModel.role == "user")
        return await self.session.scalar(statement)

    async def get_assistant_message_for_run(self, run_id: str) -> MessageModel | None:
        """获取某运行对应的助手消息，用于保证终态消息幂等写入。"""
        statement = select(MessageModel).where(
            MessageModel.run_id == run_id,
            MessageModel.role == "assistant",
        )
        return await self.session.scalar(statement)

    async def search_conversation_history(self, query: str, limit: int) -> list[dict[str, Any]]:
        """在对话历史全文索引中搜索，返回命中的对话摘要（去重，最多 ``limit`` 条）。

        仅 SQLite 且 ``query`` 可解析出长度 >= 3 的词条时生效；用 ``MATCH`` 做
        trigram 分词匹配，``candidate_limit`` 取 ``max(limit*5, limit)`` 以扩大候选
        再按对话去重，最终按 ``snippet`` 截断展示。
        """
        terms = [term.replace('"', "") for term in query.split() if len(term.replace('"', "")) >= 3]
        if not terms or not self.session.bind or self.session.bind.dialect.name != "sqlite":
            return []
        # 多词以 AND 连接，要求所有词都命中（由 >3 字符的词组成）
        expression = " AND ".join(f'"{term}"' for term in terms)
        rows = await self.session.execute(
            text("""SELECT conversation_id, title,
                snippet(conversation_history_fts, 4, '', '', '…', 32) AS snippet
            FROM conversation_history_fts
            WHERE conversation_history_fts MATCH :query
            ORDER BY rank LIMIT :candidate_limit"""),
            {"query": expression, "candidate_limit": max(limit * 5, limit)},
        )
        matches = []
        seen = set()
        for row in rows:
            if row.conversation_id in seen:
                continue
            seen.add(row.conversation_id)
            matches.append(
                {
                    "conversationId": row.conversation_id,
                    "title": row.title,
                    "snippet": row.snippet,
                }
            )
            if len(matches) >= limit:
                break
        return matches

    async def search_current_conversation_history(
        self,
        conversation_id: str,
        query: str,
        limit: int,
        *,
        exclude_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """在当前会话的原始消息中搜索，返回消息级命中而不是会话目录。

        被摘要覆盖的消息仍保留在 ``messages`` 与 FTS5 中，因此可以按需恢复细节。
        ``exclude_run_id`` 用于排除当前问题及其回答，避免查询命中自身。
        """
        terms = [term.replace('"', "") for term in query.split() if len(term.replace('"', "")) >= 3]
        if not terms or not self.session.bind or self.session.bind.dialect.name != "sqlite":
            return []
        expression = " AND ".join(f'"{term}"' for term in terms)
        exclude_clause = ""
        parameters: dict[str, Any] = {
            "query": expression,
            "conversation_id": conversation_id,
            "limit": max(1, limit),
        }
        if exclude_run_id:
            exclude_clause = """AND message_id NOT IN (
                SELECT id FROM messages WHERE run_id = :exclude_run_id
            )"""
            parameters["exclude_run_id"] = exclude_run_id
        result = await self.session.execute(
            text(f"""SELECT message_id, role,
                snippet(conversation_history_fts, 4, '', '', '…', 40) AS snippet
            FROM conversation_history_fts
            WHERE conversation_history_fts MATCH :query
              AND conversation_id = :conversation_id
              {exclude_clause}
            ORDER BY rank LIMIT :limit"""),
            parameters,
        )
        rows = list(result)
        message_ids = [str(row.message_id) for row in rows]
        if not message_ids:
            return []
        messages = {
            message.id: message
            for message in (
                await self.session.scalars(select(MessageModel).where(MessageModel.id.in_(message_ids)))
            ).all()
        }
        # FTS rank 顺序必须保留，不能由 SQLAlchemy 的 IN 查询顺序覆盖。
        snippets = {str(row.message_id): str(row.snippet) for row in rows}
        return [
            {
                "messageId": message_id,
                "role": messages[message_id].role,
                "snippet": snippets[message_id],
                "createdAt": messages[message_id].created_at.isoformat(),
            }
            for message_id in message_ids
            if message_id in messages
        ]

    async def read_message_context(
        self,
        conversation_id: str,
        message_id: str,
        before: int,
        after: int,
    ) -> dict[str, Any]:
        """读取当前会话中命中消息及其前后原始对话，恢复指代与语境。"""
        target = await self.session.get(MessageModel, message_id)
        if (
            target is None
            or target.conversation_id != conversation_id
            or target.role not in {"user", "assistant"}
        ):
            return {"messageId": message_id, "messages": []}
        before_statement = (
            select(MessageModel)
            .where(
                MessageModel.conversation_id == conversation_id,
                MessageModel.role.in_(["user", "assistant"]),
                or_(
                    MessageModel.created_at < target.created_at,
                    and_(MessageModel.created_at == target.created_at, MessageModel.id < target.id),
                ),
            )
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(max(0, before))
        )
        after_statement = (
            select(MessageModel)
            .where(
                MessageModel.conversation_id == conversation_id,
                MessageModel.role.in_(["user", "assistant"]),
                or_(
                    MessageModel.created_at > target.created_at,
                    and_(MessageModel.created_at == target.created_at, MessageModel.id > target.id),
                ),
            )
            .order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
            .limit(max(0, after))
        )
        previous = list(reversed(list((await self.session.scalars(before_statement)).all())))
        following = list((await self.session.scalars(after_statement)).all())
        messages = [*previous, target, *following]
        return {
            "messageId": message_id,
            "messages": [
                {
                    "id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "createdAt": message.created_at.isoformat(),
                    "matched": message.id == message_id,
                }
                for message in messages
            ],
        }

    async def read_conversation_history(self, conversation_id: str, limit: int) -> dict[str, Any]:
        """读取用于喂给模型的对话上下文：标题、摘要与最近 ``limit`` 条 user/assistant 消息。

        过滤掉 system 等内部消息，仅保留 user/assistant；当消息数超过 ``limit`` 时
        取末尾 ``limit`` 条（保证 ``max(1, limit)`` 至少 1 条），实现简单滑动窗口。
        """
        conversation = await self.get_conversation(conversation_id)
        if conversation is None:
            return {"conversationId": conversation_id, "title": "", "summary": "", "messages": []}
        messages = [item for item in await self.list_messages(conversation_id) if item.role in {"user", "assistant"}]
        return {
            "conversationId": conversation.id,
            "title": conversation.title,
            "summary": conversation.summary or "",
            "messages": [
                {
                    "id": item.id,
                    "role": item.role,
                    "content": item.content,
                    "createdAt": item.created_at.isoformat(),
                }
                for item in messages[-max(1, limit):]
            ],
        }

    async def upsert_message_memory(
        self, *, message: MessageModel, datasource_id: str, importance: float = 0.5
    ) -> MemoryItemModel:
        """由一条消息派生并保存记忆条目（按 ``source_message_id`` 幂等，已存在则跳过）。

        用于把对话内容沉淀为可被后续检索的长期记忆；``kind`` 固定为
        ``conversation_message``，并记录来源角色与运行 ID。
        """
        statement = select(MemoryItemModel).where(MemoryItemModel.source_message_id == message.id)
        memory = await self.session.scalar(statement)
        if memory is None:
            memory = MemoryItemModel(
                id=new_id("mem"),
                conversation_id=message.conversation_id,
                datasource_id=datasource_id,
                kind="conversation_message",
                content=message.content,
                source_message_id=message.id,
                importance=importance,
                metadata_json={"role": message.role, "runId": message.run_id},
            )
            self.session.add(memory)
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def list_memory_items(self, conversation_id: str) -> list[MemoryItemModel]:
        """列出某对话下的全部记忆条目，按创建时间升序。"""
        statement = (
            select(MemoryItemModel)
            .where(MemoryItemModel.conversation_id == conversation_id)
            .order_by(MemoryItemModel.created_at.asc())
        )
        return list((await self.session.scalars(statement)).all())

    async def get_memory_item(self, memory_id: str) -> MemoryItemModel | None:
        """按 ID 获取单条记忆条目。"""
        return await self.session.get(MemoryItemModel, memory_id)

    async def delete_memory_item(self, memory: MemoryItemModel) -> None:
        """删除一条记忆条目。"""
        await self.session.delete(memory)
        await self.session.commit()

    async def get_summary_state(self, conversation_id: str) -> ConversationSummaryStateModel | None:
        """获取对话的摘要进度状态（一对一并以 conversation_id 为主键）。"""
        return await self.session.get(ConversationSummaryStateModel, conversation_id)

    async def save_conversation_summary(
        self,
        *,
        conversation: ConversationModel,
        summary: str,
        last_message_id: str,
        summarized_message_count: int,
    ) -> ConversationSummaryStateModel:
        """保存/更新对话摘要，并同步更新对话实体上的 ``summary`` 字段。

        首次时新建摘要状态记录；之后仅更新进度与摘要内容，便于下次增量摘要。
        """
        state = await self.get_summary_state(conversation.id)
        if state is None:
            state = ConversationSummaryStateModel(conversation_id=conversation.id)
            self.session.add(state)
        state.last_message_id = last_message_id
        state.summarized_message_count = summarized_message_count
        state.updated_at = utc_now()
        conversation.summary = summary
        conversation.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(state)
        return state

    async def enforce_memory_retention(
        self, *, conversation_id: str, ttl_days: int, max_items: int
    ) -> list[str]:
        """执行记忆保留策略：按 TTL 过期 + 容量上限淘汰，返回被删除条目的 ID 列表。

        逻辑：先剔除超过 ``ttl_days`` 未更新的条目；若剩余仍超过 ``max_items``，
        再按「优先保留 conversation_message 类、重要度高的、最近更新的」排序逐出差额。
        """
        items = await self.list_memory_items(conversation_id)
        now = utc_now()
        # 1) 先按 TTL 标记过期条目
        expired = {
            item.id
            for item in items
            if ttl_days > 0 and _aware(item.updated_at) < now - timedelta(days=ttl_days)
        }
        remaining = [item for item in items if item.id not in expired]
        # 2) 若仍超容量，按淘汰优先级（kind 优先、重要度高优先、更新新优先）排序逐出
        overflow = max(0, len(remaining) - max(0, max_items))
        if overflow:
            eviction_order = sorted(
                remaining,
                key=lambda item: (
                    item.kind != "conversation_message",  # conversation_message 类最优先保留
                    float(item.importance),  # 重要度高者优先保留
                    _aware(item.updated_at),  # 更新时间新者优先保留
                ),
            )
            expired.update(item.id for item in eviction_order[:overflow])
        if expired:
            await self.session.execute(delete(MemoryItemModel).where(MemoryItemModel.id.in_(expired)))
            await self.session.commit()
        return sorted(expired)

    async def apply_long_term_memory(
        self,
        *,
        conversation_id: str,
        datasource_id: str,
        source_message_id: str,
        action: str,
        key: str,
        kind: str,
        content: str,
        confidence: float,
    ) -> tuple[MemoryItemModel | None, str | None]:
        """应用一条长期记忆指令（新增/更新/删除），按 ``memoryKey`` 去重。

        - ``action == "delete"``：删除匹配 ``key`` 的已有条目，返回 ``(None, 删除ID)``。
        - 其他 action：按 ``key`` 查找；不存在则新建，存在则覆盖内容与重要度。
        重要度由 ``confidence`` 映射（下限 0.5、上限 1.0），``metadata_json`` 记录
        ``memoryKey``/``confidence``/``sourceMessageId``。

        返回 ``(memory, deleted_id)``：新建/更新时为 ``(memory, None)``，删除时为
        ``(None, deleted_id)``，未找到待删时为 ``(None, None)``。
        """
        items = await self.list_memory_items(conversation_id)
        # 仅匹配非 conversation_message 类的长期记忆，并以 metadata 中的 memoryKey 定位
        existing = next(
            (
                item
                for item in items
                if item.kind != "conversation_message" and (item.metadata_json or {}).get("memoryKey") == key
            ),
            None,
        )
        if action == "delete":
            if existing is None:
                return None, None
            deleted_id = existing.id
            await self.session.delete(existing)
            await self.session.commit()
            return None, deleted_id
        metadata = {
            "memoryKey": key,
            "confidence": confidence,
            "sourceMessageId": source_message_id,
        }
        if existing is None:
            existing = MemoryItemModel(
                id=new_id("mem"),
                conversation_id=conversation_id,
                datasource_id=datasource_id,
                kind=kind,
                content=content,
                source_message_id=None,
                importance=min(1.0, max(0.5, confidence)),
                metadata_json=metadata,
            )
            self.session.add(existing)
        else:
            existing.kind = kind
            existing.content = content
            existing.importance = min(1.0, max(0.5, confidence))
            existing.metadata_json = metadata
            existing.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(existing)
        return existing, None


def _aware(value):
    """为缺失时区的 datetime 补齐 UTC 时区信息，便于安全做时间比较。"""
    return value if value.tzinfo else value.replace(tzinfo=utc_now().tzinfo)
