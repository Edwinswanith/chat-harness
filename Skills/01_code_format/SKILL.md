# Code Format & Cross-File Calling Skill

## Purpose

Use this skill to control how code is written, split, imported, instantiated, and called across files in the AI harness codebase.

This skill is about:
- file size discipline
- naming
- imports
- class/function boundaries
- dependency direction
- dependency injection
- cross-file calls
- orchestration wiring
- avoiding circular dependencies
- keeping each module small and understandable

This skill does not define business behavior. It defines how implementation code is structured.

---

## 1. Hard File Size Rule

Hard rule:

```text
No source file may exceed 700 lines.
```

Target:

```text
Prefer 200-500 lines per file.
Split files before they approach 600-650 lines.
```

Important:

```text
Do NOT pad a small file to reach 500 lines.
A 40-line file is valid if that is all the responsibility needs.
```

The user's intent is to prevent oversized files, not to force unnecessary code.

When a file exceeds ~500 lines, inspect whether it contains more than one responsibility.

Split by responsibility before 700 lines.

---

## 2. One Primary Responsibility Per File

Good:

```text
orchestrator.py
tool_orchestrator.py
memory_service.py
rag_service.py
artifact_validator.py
sandbox_worker.py
```

Bad:

```text
agent.py
everything.py
helpers.py
common.py
manager.py
```

A file may contain closely related small types, but should have one primary responsibility.

---

## 3. Naming Rules

Python:

```text
snake_case.py
PascalCase class names
snake_case functions
UPPER_CASE constants
```

TypeScript:

```text
PascalCase.tsx for React components
camelCase.ts for hooks/services
PascalCase interfaces/types only when project conventions use it
```

Recommended suffixes:

```text
*_service.py
*_repository.py
*_client.py
*_worker.py
*_validator.py
*_registry.py
*_manager.py
*_orchestrator.py
*_adapter.py
```

---

## 4. Cross-File Calling Principle

Files should communicate through explicit interfaces.

Preferred call path:

```text
API Route
  ↓
Application Service
  ↓
Run Orchestrator
  ↓
Specialized Service / Registry / Manager
  ↓
Repository / Provider / Worker / Adapter
```

Avoid arbitrary file-to-file calls.

Bad:

```text
api/messages.py
  directly imports docker_runner.py
```

Good:

```text
api/messages.py
  → chat_service.py
  → run_service.py
  → orchestrator.py
  → tool_orchestrator.py
  → sandbox job service
```

---

## 5. Dependency Direction

Allowed high-level direction:

```text
api
  ↓
services
  ↓
harness
  ↓
memory / rag / tools / subagents / validation
  ↓
repositories / providers / storage / queue
```

Workers may depend on:
- repositories
- storage
- queue
- provider clients
- job models

Workers should not depend on frontend.

Sandbox-service must not import backend repositories.

---

## 6. Orchestrator Wiring

The orchestrator should receive dependencies, not construct everything internally.

Bad:

```python
class RunOrchestrator:
    def __init__(self):
        self.memory = MemoryService(...)
        self.tools = ToolOrchestrator(...)
        self.rag = RagService(...)
```

Good:

```python
class RunOrchestrator:
    def __init__(
        self,
        planner,
        context_builder,
        memory_service,
        rag_service,
        model_client,
        tool_orchestrator,
        subagent_manager,
        validator,
        finalizer,
    ):
        self.planner = planner
        self.context_builder = context_builder
        self.memory = memory_service
        self.rag = rag_service
        self.model = model_client
        self.tools = tool_orchestrator
        self.subagents = subagent_manager
        self.validator = validator
        self.finalizer = finalizer
```

Construct these in a container/factory/bootstrap file.

---

## 7. Dependency Container / Factory

Use one place to wire dependencies.

Example:

```python
class AppContainer:
    def __init__(self, settings):
        self.run_repo = RunRepository(...)
        self.tool_run_repo = ToolRunRepository(...)

        self.memory_service = MemoryService(...)
        self.rag_service = RagService(...)
        self.tool_registry = ToolRegistry(...)
        self.tool_orchestrator = ToolOrchestrator(
            registry=self.tool_registry,
            permission_service=PermissionService(...),
            tool_run_repo=self.tool_run_repo,
        )

        self.subagent_manager = SubAgentManager(...)
        self.validator = ValidationService(...)
        self.model_client = DeepSeekClient(...)

        self.orchestrator = RunOrchestrator(
            planner=Planner(self.model_client),
            context_builder=ContextBuilder(...),
            memory_service=self.memory_service,
            rag_service=self.rag_service,
            model_client=self.model_client,
            tool_orchestrator=self.tool_orchestrator,
            subagent_manager=self.subagent_manager,
            validator=self.validator,
            finalizer=Finalizer(...),
        )
```

Do not instantiate core services inside API routes.

---

## 8. Cross-File Function Calling

If `orchestrator.py` needs memory:

```python
memory = await self.memory.retrieve_for_request(...)
```

If it needs a tool:

```python
tool_result = await self.tools.execute(...)
```

If it needs a sub-agent:

```python
sub_result = await self.subagents.run_agent(...)
```

If it needs validation:

```python
validation = await self.validator.validate(...)
```

Do not import and call low-level functions directly when a service boundary exists.

---

## 9. Interface First

When a component can have multiple implementations, define a base protocol/interface.

Example:

```python
from typing import Protocol

class ModelClient(Protocol):
    async def call(self, messages, tools=None) -> dict:
        ...
```

Example:

```python
class VectorStore(Protocol):
    async def search(self, query_vector, filters, top_k):
        ...

    async def upsert(self, points):
        ...
```

Use interfaces for:
- model clients
- storage providers
- vector stores
- queue adapters
- sandbox clients

Do not create interfaces for trivial one-off functions.

---

## 10. Imports

Prefer absolute imports inside backend package:

```python
from app.harness.orchestrator import RunOrchestrator
from app.tools.registry import ToolRegistry
```

Avoid deep relative imports such as:

```python
from ....tools.registry import ToolRegistry
```

Keep imports at top of file except for deliberate lazy imports to break optional dependency cycles.

---

## 11. Avoid Circular Dependencies

Bad:

```text
orchestrator.py imports tools.py
tools.py imports orchestrator.py
```

Fix by extracting shared types/interfaces:

```text
harness/types.py
tools/types.py
shared/contracts.py
```

Preferred:

```text
orchestrator → tool_orchestrator
tool_orchestrator → tool registry
tool registry → tool implementations
```

Never:

```text
tool implementation → orchestrator
```

Tools return structured results instead.

---

## 12. Structured Results

Cross-file boundaries should pass typed data.

Example:

```python
class ToolResult(BaseModel):
    status: str
    data: dict | None = None
    error: str | None = None
    artifact_ids: list[str] = []
```

Avoid returning random dictionaries with different shapes from every tool.

---

## 13. Error Boundaries

Low-level modules raise typed errors.

Example:

```python
class ToolExecutionError(Exception):
    pass
```

Application layer converts them into structured results.

API layer converts application errors into HTTP errors.

Do not raise `HTTPException` from repositories or tool implementations.

---

## 14. Async Rules

Use `async` for:
- LLM API calls
- DB calls
- object storage calls
- Redis calls
- external API calls
- tool execution that is async

Do not use blocking I/O in FastAPI request handlers.

Heavy CPU work belongs in workers/sandbox.

---

## 15. Orchestrator Must Stay Thin

The orchestrator should read like workflow code.

Good:

```python
plan = await self.planner.create_plan(...)
memory = await self.memory.retrieve_for_request(...)
decision = await self.model.call(...)
result = await self.tools.execute(...)
validation = await self.validator.validate(...)
```

Bad:
- raw Mongo queries
- Docker commands
- HTTP provider payload construction
- file parsing
- vector math

---

## 16. File Split Rules

Split a file when:
- it has two unrelated classes
- it has API + business logic
- it has orchestration + provider code
- it has >500-600 lines and clear sub-responsibilities
- tests become hard to isolate

Example:

```text
tool_orchestrator.py
```

can split into:

```text
tool_orchestrator.py
tool_permissions.py
tool_result.py
tool_execution_policy.py
```

only if those responsibilities are real.

---

## 17. Function Size

Prefer:
- 10-50 lines for ordinary functions
- 50-100 lines only when flow is genuinely linear
- split very large functions into named steps

Avoid 200-line functions.

---

## 18. Class Size

A class should represent one cohesive responsibility.

If a class contains:
- DB logic
- prompt logic
- tool execution
- validation
- storage

it is too broad.

---

## 19. Public vs Private Methods

Use public methods for external boundaries:

```python
await memory_service.retrieve_for_request(...)
```

Use `_private_method()` for internal helper logic.

Do not call private methods across modules.

---

## 20. DTO / Schema Boundaries

Use typed request/result models across major boundaries:

```text
PlannerInput / PlannerResult
ToolCall / ToolResult
ValidationResult
SubAgentTask / SubAgentResult
MemoryBundle
RagContext
RunResult
```

This makes orchestration predictable.

---

## 21. Orchestrator Link Map

Canonical link map:

```text
RunOrchestrator
├── Planner
├── ContextBuilder
├── MemoryService
├── RagService
├── ModelClient
├── ToolOrchestrator
│   └── ToolRegistry
│       └── Tool Implementations
├── SubAgentManager
│   └── SubAgentRegistry
├── ValidationService
└── Finalizer
```

The orchestrator coordinates these services. It does not own their low-level implementation.

---

## 22. Rule for AI Coding Agent

Before adding code:

1. identify the responsibility
2. identify the correct file
3. check file line count
4. if target file is approaching 600 lines, consider a split
5. avoid creating a new abstraction unless required
6. update imports
7. run tests
8. report changed files

---

## 23. Review Checklist

Before finishing any code change:

```text
[ ] No source file >700 lines
[ ] No artificial padding to reach 500 lines
[ ] Each file has one primary responsibility
[ ] Orchestrator stays control-flow focused
[ ] No low-level DB/Docker/provider logic inside orchestrator
[ ] No circular imports
[ ] Cross-file calls use explicit interfaces/services
[ ] Tool outputs are structured
[ ] Sub-agent outputs are structured
[ ] Validation results are structured
[ ] Imports resolve
[ ] Tests pass
```
