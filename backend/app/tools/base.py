from typing import Protocol
from app.schemas.contracts import ToolResult


class Tool(Protocol):
    name: str
    description: str
    schema: type

    async def execute(self, scope, run, arguments) -> ToolResult: ...
