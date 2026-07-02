from typing import Any

from sqlalchemy import delete, select

from app.infrastructure.persistence.models import ConversationModel, MessageModel, utc_now
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class ConversationRepository(RepositoryBase):
    async def create_conversation(self, *, title: str, agent_id: str, datasource_id: str) -> ConversationModel:
        conversation = ConversationModel(
            id=new_id("conv"), title=title, agent_id=agent_id, datasource_id=datasource_id
        )
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_conversation(self, conversation_id: str) -> ConversationModel | None:
        return await self.session.get(ConversationModel, conversation_id)

    async def list_conversations(self, query: str | None, limit: int) -> list[ConversationModel]:
        statement = select(ConversationModel).order_by(ConversationModel.updated_at.desc()).limit(limit)
        if query:
            statement = statement.where(ConversationModel.title.ilike(f"%{query.strip()}%"))
        return list((await self.session.scalars(statement)).all())

    async def update_conversation(self, conversation: ConversationModel, **changes: Any) -> ConversationModel:
        for key, value in changes.items():
            if value is not None:
                setattr(conversation, key, value)
        conversation.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def delete_conversation(self, conversation_id: str) -> bool:
        result = await self.session.execute(delete(ConversationModel).where(ConversationModel.id == conversation_id))
        await self.session.commit()
        return bool(result.rowcount)

    async def add_message(
        self, *, conversation_id: str, run_id: str | None, role: str, content: str
    ) -> MessageModel:
        message = MessageModel(
            id=new_id("msg"), conversation_id=conversation_id, run_id=run_id, role=role, content=content
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def list_messages(self, conversation_id: str) -> list[MessageModel]:
        statement = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc())
        )
        return list((await self.session.scalars(statement)).all())

