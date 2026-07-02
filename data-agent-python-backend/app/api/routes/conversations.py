from fastapi import APIRouter, Query, status

from app.api.dependencies import SessionDependency
from app.api.presenters import conversation_detail, conversation_summary
from app.api.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
    ConversationUpdate,
    OperationResponse,
)
from app.application import ConversationService
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.repository import Repository


router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
async def create_conversation(body: ConversationCreate, session: SessionDependency) -> ConversationSummary:
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


@router.delete("/{conversation_id}", response_model=OperationResponse)
async def delete_conversation(conversation_id: str, session: SessionDependency) -> OperationResponse:
    if not await Repository(session).delete_conversation(conversation_id):
        raise ResourceNotFoundError("conversation", conversation_id)
    return OperationResponse(ok=True, status="deleted", message="会话已删除")

