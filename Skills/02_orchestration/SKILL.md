# Orchestration Skill

## Purpose
Build and maintain the workflow controller that decides what happens next.

## Responsibilities
The orchestrator:
- creates/loads run state
- invokes planning
- retrieves memory/RAG context
- calls the model
- routes tool requests
- routes sub-agent requests
- invokes validation
- handles feedback/retry
- finalizes result

It must not implement low-level tool logic, DB queries, Docker execution, or vector search.

## Canonical Flow

```text
request
→ create run
→ plan
→ retrieve context
→ model decision
→ tool/sub-agent/direct
→ validate
→ feedback/retry
→ finalize
```

## Main Interface

```python
class RunOrchestrator:
    async def run(self, run_id: str) -> RunResult:
        ...
```

## State Machine

```text
created
planning
context_building
model_running
tool_running
subagent_running
validating
repairing
completed
failed
cancelled
```

## Dependencies
Inject:
- Planner
- ContextBuilder
- MemoryService
- RagService
- ModelClient
- ToolOrchestrator
- SubAgentManager
- ValidationService
- Finalizer

## Rules
- no raw Mongo calls
- no direct Docker SDK
- no provider-specific HTTP payloads
- max retry/tool limits
- every state transition persisted
- every external action idempotent when possible
