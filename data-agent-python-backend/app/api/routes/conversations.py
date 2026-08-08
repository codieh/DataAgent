"""会话相关路由：CRUD、记忆管理与会话级删除。

所有接口均绑定 ``/conversations`` 前缀。涉及运行（run）的任务取消与记忆清理
会直接联动应用层的任务注册表与图运行时（graph_runtime）。
"""

import asyncio
import logging

from fastapi import APIRouter, Query, status

from app.api.dependencies import SessionDependency
from app.api.presenters import conversation_detail, conversation_summary
from app.api.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
    ConversationUpdate,
    MemoryItemResponse,
    MemoryListResponse,
    OperationResponse,
)
from app.application import ConversationService
from app.application.tasks import TERMINAL_STATUSES, task_registry
from app.application.executor import graph_runtime
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.repository import Repository


router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
async def create_conversation(body: ConversationCreate, session: SessionDependency) -> ConversationSummary:
    # 标题缺省时使用占位文案
    conversation = await Repository(session).create_conversation(
        title=body.title or "新建分析",
        agent_id=body.agent_id,
        datasource_id=body.datasource_id,
    )
    return conversation_summary(conversation)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    session: SessionDependency,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> ConversationListResponse:
    items = await Repository(session).list_conversations(q, limit)
    return ConversationListResponse(items=[conversation_summary(item) for item in items])


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, session: SessionDependency) -> ConversationDetail:
    # 会话详情走应用层服务以聚合消息与运行
    return conversation_detail(await ConversationService(session).detail(conversation_id))


@router.patch("/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    session: SessionDependency,
) -> ConversationSummary:
    repository = Repository(session)
    conversation = await repository.get_conversation(conversation_id)
    if not conversation:
        raise ResourceNotFoundError("conversation", conversation_id)
    conversation = await repository.update_conversation(
        conversation,
        title=body.title,
        agent_id=body.agent_id,
        datasource_id=body.datasource_id,
    )
    return conversation_summary(conversation)


@router.get("/{conversation_id}/memories", response_model=MemoryListResponse)
async def list_long_term_memories(conversation_id: str, session: SessionDependency) -> MemoryListResponse:
    repository = Repository(session)
    if not await repository.get_conversation(conversation_id):
        raise ResourceNotFoundError("conversation", conversation_id)
    # 排除「会话消息」类型的记忆，仅对外暴露长期记忆
    memories = [
        item for item in await repository.list_memory_items(conversation_id) if item.kind != "conversation_message"
    ]
    return MemoryListResponse(
        items=[
            MemoryItemResponse(
                id=item.id,
                kind=item.kind,
                content=item.content,
                importance=item.importance,
                metadata=item.metadata_json,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in memories
        ]
    )


@router.delete("/{conversation_id}/memories/{memory_id}", response_model=OperationResponse)
async def delete_long_term_memory(
    conversation_id: str, memory_id: str, session: SessionDependency
) -> OperationResponse:
    repository = Repository(session)
    memory = await repository.get_memory_item(memory_id)
    # 校验归属同一会话且非会话消息，否则视为不存在
    if not memory or memory.conversation_id != conversation_id or memory.kind == "conversation_message":
        raise ResourceNotFoundError("memory", memory_id)
    await repository.delete_memory_item(memory)
    # 同时从图运行时的记忆提供者中移除，保持双写一致
    await graph_runtime.memory_provider.delete([memory_id])
    return OperationResponse(ok=True, status="deleted", message="长期记忆已删除")


@router.delete("/{conversation_id}", response_model=OperationResponse)
async def delete_conversation(conversation_id: str, session: SessionDependency) -> OperationResponse:
    repository = Repository(session)
    if not await repository.get_conversation(conversation_id):
        raise ResourceNotFoundError("conversation", conversation_id)
    memory_ids = [item.id for item in await repository.list_memory_items(conversation_id)]
    runs = await repository.list_runs(conversation_id)
    run_ids = [run.id for run in runs]
    result_sets = await repository.list_conversation_result_sets(conversation_id)
    dataset_paths = [item.file_path for item in result_sets if item.file_path]
    # 删除前先取消仍在进行中的任务，避免孤儿任务继续运行
    for run in runs:
        if run.status not in TERMINAL_STATUSES:
            await task_registry.cancel_and_wait(run.id)
    if not await repository.delete_conversation(conversation_id):
        raise ResourceNotFoundError("conversation", conversation_id)
    # 数据库提交后清理三个外部存储。全部任务都会执行，任一失败都会明确返回错误，
    # 避免 CSV、向量记忆或 checkpoint 的清理异常被静默忽略。
    cleanup_results = await asyncio.gather(
        graph_runtime.memory_provider.delete(memory_ids),
        graph_runtime.dataset_store.delete_files(dataset_paths),
        graph_runtime.delete_checkpoints(run_ids),
        return_exceptions=True,
    )
    cleanup_names = ("memory", "dataset_files", "checkpoints")
    failures = [
        f"{name}: {result}"
        for name, result in zip(cleanup_names, cleanup_results, strict=True)
        if isinstance(result, BaseException)
    ]
    if failures:
        logger.error(
            "conversation external cleanup failed: conversationId=%s runCount=%d datasetCount=%d errors=%s",
            conversation_id,
            len(run_ids),
            len(dataset_paths),
            failures,
        )
        raise RuntimeError("会话数据库记录已删除，但外部资源清理失败：" + "; ".join(failures))
    logger.info(
        "conversation deleted: conversationId=%s runs=%d datasetFiles=%d checkpoints=%d memories=%d",
        conversation_id,
        len(run_ids),
        cleanup_results[1],
        cleanup_results[2],
        len(memory_ids),
    )
    return OperationResponse(ok=True, status="deleted", message="会话及关联资源已删除")
