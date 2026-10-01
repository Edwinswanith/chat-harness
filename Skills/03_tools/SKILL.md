# Tools Skill

## Purpose
Define safe, typed, permission-aware actions that agents can request.

## Core Components
```text
ToolRegistry
ToolOrchestrator
Tool schemas
Tool implementations
ToolRun persistence
```

## Tool Contract

```python
class Tool:
    name: str
    description: str

    async def execute(self, context, arguments) -> ToolResult:
        ...
```

## ToolResult

```python
class ToolResult(BaseModel):
    status: Literal["success", "error"]
    data: dict | None = None
    error_code: str | None = None
    error: str | None = None
    artifact_ids: list[str] = []
```

## Flow
```text
model requests tool
→ registry lookup
→ schema validation
→ permission check
→ quota/risk check
→ create ToolRun
→ execute or enqueue job
→ validate result
→ return structured ToolResult
```

## Rules
- one tool = one clear purpose
- no raw unrestricted shell tool
- no raw DB tool unless deliberately scoped
- high-risk actions require confirmation
- heavy tools use jobs/workers
- every tool call is logged
