from typing import Any, Protocol, TypeVar

from pydantic import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)


class LlmClient(Protocol):
    async def complete(self, system: str, user: str, *, max_tokens: int | None = None) -> str: ...

    async def complete_json(
        self, system: str, user: str, *, max_tokens: int | None = None
    ) -> dict[str, Any]: ...

    async def complete_model(
        self, output_type: type[ModelT], system: str, user: str, *, max_tokens: int | None = None
    ) -> ModelT: ...
