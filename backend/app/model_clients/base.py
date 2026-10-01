from typing import Protocol
from app.schemas.contracts import Decision, ModelContext


class ModelClient(Protocol):
    async def call(self, context: ModelContext) -> Decision: ...
