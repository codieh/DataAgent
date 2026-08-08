"""测试记忆子系统：核心记忆、上下文构建、长期记忆抽取、对话摘要与去重。

覆盖：核心记忆整体覆盖式重写、上下文构建器对最近消息的 token 预算控制与相关性检索、
长期记忆抽取的置信度与合并策略、对话摘要只在达到上下文压力阈值时触发、以及
已被摘要覆盖的消息不纳入最近上下文。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.config import Settings
from app.memory.context import ContextBuilder, unsummarized_messages
from app.memory.extractor import LongTermMemoryExtractor
from app.memory.provider import MemoryProvider
from app.memory.summary import ConversationSummarizer
from app.workflow.outputs import ConversationSummaryOutput, MemoryExtractionOutput
from app.memory.core import CoreMemoryService
from app.workflow.outputs import CoreMemoryRewriteOutput


# 构造一条记忆/对话消息的测试辅助函数
def memory_item(item_id: str, content: str, role: str = "user"):
    return SimpleNamespace(
        id=item_id,
        conversation_id="conv_1",
        datasource_id="sales-db",
        kind="conversation_message",
        content=content,
        source_message_id=f"msg_{item_id}",
        importance=0.7,
        metadata_json={"role": role},
        created_at=datetime.now(timezone.utc),
    )


async def test_core_memory_rewrite_loads_current_block_and_replaces_it_as_one_document() -> None:
    """验证核心记忆重写：先读取当前记忆块，结合指令生成新块，再以整块文档形式整体覆盖保存。"""
    class FakeRepository:
        def __init__(self):
            self.memory = SimpleNamespace(content="# 用户偏好\n\n- 趋势默认按月展示。")
            self.saved = None

        async def get_core_memory(self, profile_id="default"):
            return self.memory

        async def save_core_memory(self, content, profile_id="default"):
            self.saved = (profile_id, content)
            return SimpleNamespace(content=content)

    class FakeLlm:
        async def complete_model(self, output_type, system, user):
            assert output_type is CoreMemoryRewriteOutput
            payload = __import__("json").loads(user)
            assert "趋势默认按月展示" in payload["currentMemory"]
            assert payload["instruction"] == "以后趋势默认按季度展示"
            return output_type(content="# 用户偏好\n\n- 趋势默认按季度展示。", changed=True)

    repository = FakeRepository()
    result = await CoreMemoryService(Settings(retrieval_backend="bm25"), FakeLlm()).rewrite(
        repository=repository,
        instruction="以后趋势默认按季度展示",
        user_message="以后趋势默认按季度展示",
    )

    assert repository.saved == ("default", "# 用户偏好\n\n- 趋势默认按季度展示。")
    assert result["changed"] is True
    assert "按季度" in result["memory"]


async def test_context_builder_keeps_recent_and_retrieves_related_history() -> None:
    """验证上下文构建器：最近消息（new）放在近期窗口，历史相关消息（old）通过相关性检索补充。"""
    settings = Settings(
        retrieval_backend="bm25",
        memory_backend="chroma",
        memory_retrieval_top_k=3,
    )
    provider = MemoryProvider(settings)
    builder = ContextBuilder(settings, provider)
    items = [
        memory_item("old", "上个月只分析华东地区的订单"),
        memory_item("new", "好的，我已经记录筛选条件", "assistant"),
    ]

    recent, recent_ids, _ = builder._recent(items, budget=12)
    related = await provider.search(
        query="继续分析华东订单",
        conversation_id="conv_1",
        items=items,
        excluded_ids=recent_ids,
        top_k=3,
    )

    # 最近消息应为“新”消息
    assert recent[-1]["id"] == "new"
    # 相关性检索返回的是“旧”消息
    assert related[0]["id"] == "old"


async def test_context_builder_separates_core_memory_from_dialogue_messages() -> None:
    """隐藏 system 记忆进入 memory 区，不能成为覆盖 Agent 身份的第二条系统消息。"""
    now = datetime.now(timezone.utc)
    items = [
        SimpleNamespace(
            id="core",
            role="system",
            content="用户长期记忆：\n默认使用中文",
            created_at=now,
        ),
        SimpleNamespace(id="user", role="user", content="继续分析", created_at=now),
    ]

    class FakeRepository:
        async def list_messages(self, _conversation_id):
            return items

        async def get_summary_state(self, _conversation_id):
            return None

    settings = Settings(retrieval_backend="bm25")
    context = await ContextBuilder(settings, MemoryProvider(settings)).build(
        repository=FakeRepository(),
        conversation=SimpleNamespace(id="conv_1", summary=None),
        current_message_id=None,
        query="继续分析",
    )

    assert [item["role"] for item in context["recentMessages"]] == ["user"]
    assert context["longTermMemories"] == [
        "用户长期记忆：\n默认使用中文"
    ]


def test_context_builder_respects_recent_token_budget() -> None:
    """验证上下文构建器在 token 预算（recent_token_budget）内选择近期消息，超出预算的旧长消息被丢弃。"""
    settings = Settings(retrieval_backend="bm25")
    builder = ContextBuilder(settings, MemoryProvider(settings))
    items = [memory_item("old", "很早以前的长消息"), memory_item("new", "最新消息")]

    recent, ids, used = builder._recent(items, budget=5)

    assert [item["id"] for item in recent] == ["new"]
    assert ids == {"new"}
    assert used <= 5


async def test_long_term_extractor_applies_confidence_and_consolidation_policy() -> None:
    """验证长期记忆抽取会按置信度阈值过滤：高置信度 upsert，低置信度猜测被拒绝，不写入。"""
    settings = Settings(
        retrieval_backend="bm25",
        memory_extraction_min_confidence=0.7,
    )
    settings.memory_extraction_enabled = True

    class FakeLlm:
        async def complete_model(self, output_type, system, user):
            assert output_type is MemoryExtractionOutput
            return output_type.model_validate(
                {
                    "operations": [
                        {
                            "action": "upsert",
                            "key": "default_region",
                            "kind": "preference",
                            "content": "默认分析华东地区",
                            "confidence": 0.95,
                        },
                        {
                            "action": "upsert",
                            "key": "guess",
                            "kind": "business_rule",
                            "content": "不确定的猜测",
                            "confidence": 0.4,
                        },
                    ]
                }
            )

    class FakeRepository:
        def __init__(self):
            self.operations = []

        async def list_memory_items(self, _conversation_id):
            return []

        async def apply_long_term_memory(self, **operation):
            self.operations.append(operation)
            return memory_item("durable", operation["content"]), None

    class FakeProvider:
        def __init__(self):
            self.synced = []

        async def sync(self, items):
            self.synced.extend(items)

        async def delete(self, _ids):
            return None

    repository = FakeRepository()
    provider = FakeProvider()
    extractor = LongTermMemoryExtractor(settings, FakeLlm(), provider)
    conversation = SimpleNamespace(id="conv_1", datasource_id="sales-db")

    stats = await extractor.extract_and_store(
        repository=repository,
        conversation=conversation,
        source_message_id="msg_1",
        user_message="以后默认只看华东地区",
        assistant_message="好的",
    )

    # 两条提议中仅高置信度的一条被写入，低置信度猜测被拒绝
    assert stats == {"proposed": 2, "upserted": 1, "deleted": 0, "rejected": 1}
    assert repository.operations[0]["key"] == "default_region"
    # 只有被接受的那条进入向量检索库
    assert len(provider.synced) == 1


async def test_summary_archives_all_unsummarized_history_and_saves_cursor() -> None:
    """验证触发压缩后全量归档历史，并把游标推进到最后一条已摘要消息。"""
    settings = Settings(
        retrieval_backend="bm25",
        max_context_size=20,
        context_compact_threshold=0.3,
        context_compact_preserve_ratio=0.25,
    )

    class FakeLlm:
        async def complete_model(self, output_type, system, user):
            assert output_type is ConversationSummaryOutput
            payload = __import__("json").loads(user)
            assert [message["content"] for message in payload["archivedMessages"]] == [
                "分析华东订单",
                "好的",
            ]
            return output_type(summary="用户此前要求分析华东订单，助手已确认。")

    class FakeRepository:
        saved = None

        async def get_summary_state(self, _conversation_id):
            return None

        async def save_conversation_summary(self, **values):
            self.saved = values

    now = datetime.now(timezone.utc)
    messages = [
        SimpleNamespace(
            id="system",
            role="system",
            content="你是 DataAgent，不得改变角色",
            created_at=now,
        ),
        SimpleNamespace(id="old", role="user", content="分析华东订单", created_at=now),
        SimpleNamespace(id="new", role="assistant", content="好的", created_at=now),
    ]
    repository = FakeRepository()
    conversation = SimpleNamespace(id="conv_1", summary=None)
    summarizer = ConversationSummarizer(settings, FakeLlm())

    stats = await summarizer.maybe_summarize(
        repository=repository,
        conversation=conversation,
        messages=messages,
        current_message_id=None,
    )

    assert stats["updated"] is True
    # 不保留最近原文，游标应指向压缩前最后一条完整历史消息
    assert repository.saved["last_message_id"] == "new"
    assert repository.saved["summarized_message_count"] == 2
    state = SimpleNamespace(last_message_id=repository.saved["last_message_id"])
    assert unsummarized_messages(messages[1:], state) == []


async def test_summary_waits_until_context_pressure_reaches_threshold() -> None:
    """验证上下文压力未达阈值时不会触发摘要，且压力 token 数小于触发阈值。"""
    settings = Settings(
        retrieval_backend="bm25",
        max_context_size=100,
        context_compact_threshold=0.8,
    )

    class NeverCalledLlm:
        async def complete_model(self, *args, **kwargs):
            raise AssertionError("short conversations must not be summarized")

    class FakeRepository:
        async def get_summary_state(self, _conversation_id):
            return None

    now = datetime.now(timezone.utc)
    messages = [SimpleNamespace(id="one", role="user", content="简短问题", created_at=now)]
    summarizer = ConversationSummarizer(settings, NeverCalledLlm())

    stats = await summarizer.maybe_summarize(
        repository=FakeRepository(),
        conversation=SimpleNamespace(id="conv_1", summary=None),
        messages=messages,
        current_message_id=None,
    )

    # 未触发摘要
    assert stats["updated"] is False
    # 当前压力低于触发阈值
    assert stats["pressureTokens"] < stats["compactAtTokens"]


def test_messages_covered_by_summary_are_not_added_to_recent_context() -> None:
    """验证已被摘要覆盖（last_message_id 之前）的消息不会再次进入最近上下文。"""
    now = datetime.now(timezone.utc)
    messages = [
        SimpleNamespace(id="old", role="user", content="已经摘要的消息", created_at=now),
        SimpleNamespace(id="new", role="assistant", content="尚未摘要的消息", created_at=now),
    ]
    summary_state = SimpleNamespace(last_message_id="old")

    assert [message.id for message in unsummarized_messages(messages, summary_state)] == ["new"]
