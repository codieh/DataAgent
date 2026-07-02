from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class RepositoryBase:
    def __init__(self, session: AsyncSession):
        self.session = session

