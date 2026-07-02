from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ResourceNotFoundError
from app.domain.views import ConversationView
from app.infrastructure.persistence.repository import Repository


class ConversationService:
    def __init__(self, session: AsyncSession):
        self.repository = Repository(session)

    async def detail(self, conversation_id: str) -> ConversationView:
        conversation = await self.repository.get_conversation(conversation_id)
        if not conversation:
            raise ResourceNotFoundError("conversation", conversation_id)
        return ConversationView(
            conversation=conversation,
            messages=await self.repository.list_messages(conversation_id),
            runs=await self.repository.list_runs(conversation_id),
        )

