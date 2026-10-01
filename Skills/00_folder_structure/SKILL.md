# AI Harness Folder & File Structure Management Skill

## Skill Purpose

This skill exists for one narrow responsibility:

> **Create, organize, validate, and maintain the folder and file structure of an AI harness codebase without changing business logic unless structure-related refactoring is explicitly required.**

The IDE agent using this skill must act as a **repository structure architect**, not as a feature developer.

Primary goals:

- keep folder boundaries clean
- prevent files from being placed in the wrong layer
- create new files in predictable locations
- rename or move files only when there is a structural reason
- preserve imports and references after structural changes
- prevent “god files” and dumping-ground folders
- enforce consistent naming
- keep frontend, backend, workers, sandbox, tooling, memory, RAG, validation, and infrastructure clearly separated
- produce a repository that remains understandable as the harness grows

This skill is specifically for projects containing an AI chat interface, orchestration layer, tools, memory, RAG, sub-agents, validators, workers, sandboxed execution, artifacts, and related infrastructure.

---

# 1. Core Rule

The agent must always preserve this responsibility boundary:

```text
Frontend
    = user interface only

Backend API
    = authenticated request boundary

Harness
    = orchestration and AI workflow control

Model Clients
    = LLM provider adapters

Memory
    = persistent/retrieved contextual memory

RAG
    = document ingestion, embeddings, vector retrieval

Tools
    = controlled actions exposed to agents

Sub-Agents
    = specialized AI workers

Validation
    = deterministic and AI-assisted quality checks

Workers
    = asynchronous/background job execution

Sandbox Service
    = isolated untrusted code execution only

Repositories
    = persistence access

Services
    = business/application logic

Storage
    = file/object storage abstractions

Queue
    = job dispatch abstractions

Infrastructure
    = deployment/runtime configuration
```

Do not blur these boundaries.

---

# 2. Expected Top-Level Repository Structure

Use this as the default structure unless the existing repository already has a compatible equivalent:

```text
ai-harness/
├── frontend/
├── backend/
├── sandbox-service/
├── infra/
├── docs/
├── tests/
├── scripts/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

Do not create extra top-level folders without a clear architectural reason.

Avoid vague top-level folders such as:

```text
misc/
common/
temp/
stuff/
helpers/
agents-old/
new-code/
backup/
```

---

# 3. Frontend Structure

The frontend is responsible only for presentation, local UI state, API interaction, and streaming UX.

Preferred structure:

```text
frontend/
├── src/
│   ├── app/
│   │   ├── App.tsx
│   │   ├── routes.tsx
│   │   └── providers.tsx
│   │
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── Composer.tsx
│   │   │   └── StreamingMessage.tsx
│   │   │
│   │   ├── artifacts/
│   │   │   ├── ArtifactCard.tsx
│   │   │   ├── ArtifactPreview.tsx
│   │   │   └── ArtifactDownload.tsx
│   │   │
│   │   ├── jobs/
│   │   │   ├── JobStatusCard.tsx
│   │   │   ├── JobProgress.tsx
│   │   │   └── JobLogs.tsx
│   │   │
│   │   ├── sources/
│   │   │   ├── SourceStatus.tsx
│   │   │   └── SourceList.tsx
│   │   │
│   │   └── common/
│   │       ├── Button.tsx
│   │       ├── Modal.tsx
│   │       ├── Spinner.tsx
│   │       └── ErrorState.tsx
│   │
│   ├── hooks/
│   │   ├── useChat.ts
│   │   ├── useStreaming.ts
│   │   ├── useJobEvents.ts
│   │   ├── useArtifacts.ts
│   │   └── useSources.ts
│   │
│   ├── services/
│   │   ├── api.ts
│   │   ├── chatApi.ts
│   │   ├── artifactApi.ts
│   │   ├── fileApi.ts
│   │   └── jobApi.ts
│   │
│   ├── state/
│   │   ├── chatStore.ts
│   │   ├── jobStore.ts
│   │   └── uiStore.ts
│   │
│   ├── types/
│   │   ├── chat.ts
│   │   ├── artifact.ts
│   │   ├── file.ts
│   │   ├── job.ts
│   │   └── source.ts
│   │
│   └── utils/
│       └── formatters.ts
│
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## Frontend placement rules

Place code here when it:

- renders UI
- formats UI data
- subscribes to SSE/WebSocket events
- manages client-side state
- calls backend APIs

Do not place here:

- orchestration logic
- LLM provider clients
- database logic
- vector search
- permission decisions
- sandbox execution
- artifact persistence

---

# 4. Backend Structure

Preferred backend structure:

```text
backend/
├── app/
│   ├── main.py
│   │
│   ├── api/
│   ├── harness/
│   ├── model_clients/
│   ├── memory/
│   ├── rag/
│   ├── tools/
│   ├── subagents/
│   ├── validation/
│   ├── services/
│   ├── repositories/
│   ├── workers/
│   ├── storage/
│   ├── queue/
│   ├── models/
│   ├── schemas/
│   ├── core/
│   └── utils/
│
├── tests/
├── pyproject.toml
└── .env.example
```

The agent must keep backend files aligned by responsibility, not convenience.

---

# 5. API Layer

Folder:

```text
backend/app/api/
```

Recommended files:

```text
api/
├── chats.py
├── messages.py
├── runs.py
├── tools.py
├── files.py
├── artifacts.py
├── jobs.py
├── rag.py
└── health.py
```

## API layer responsibilities

API files may:

- parse HTTP requests
- validate request schemas
- resolve authenticated user/session
- call application services
- stream responses
- convert service errors into HTTP errors

API files must not directly:

- query MongoDB/Postgres
- execute tools
- call Docker
- implement RAG retrieval logic
- contain large orchestration loops
- contain provider-specific LLM code

Bad:

```python
@router.post("/messages")
async def create_message(...):
    # 300 lines of agent logic
```

Good:

```python
@router.post("/messages")
async def create_message(...):
    return await chat_service.create_message(...)
```

---

# 6. Harness Layer

Folder:

```text
backend/app/harness/
```

Recommended files:

```text
harness/
├── orchestrator.py
├── planner.py
├── context_builder.py
├── decision_engine.py
├── run_state.py
├── finalizer.py
└── events.py
```

## `orchestrator.py`

Owns:

- overall run control
- state transitions
- sequencing
- retry/repair loop
- calling planner
- calling memory
- calling model
- routing tool requests
- routing sub-agent requests
- calling validators
- finalization

Must not directly contain:

- Mongo queries
- Docker SDK code
- Qdrant code
- raw HTTP implementation for providers
- file parsing
- low-level storage code

## `planner.py`

Owns:

- structured execution planning
- task decomposition
- identifying whether tools/sub-agents are required

## `context_builder.py`

Owns:

- final LLM message/context construction
- system instructions
- memory injection
- RAG context formatting
- tool descriptions
- sub-agent result injection

## `decision_engine.py`

Owns structured routing such as:

```text
final_answer
tool_call
subagent_call
ask_user
retry
fail
```

## `run_state.py`

Owns:

- allowed orchestration states
- state transition validation

## `finalizer.py`

Owns:

- constructing final answer payload
- final message block assembly
- artifact references
- final run completion logic

---

# 7. Model Client Layer

Folder:

```text
backend/app/model_clients/
```

Recommended files:

```text
model_clients/
├── base.py
├── openai_client.py
├── deepseek_client.py
├── gemini_client.py
├── anthropic_client.py
└── mock_client.py
```

Use only files for providers that actually exist in the project.

## Rules

`base.py` defines the common interface.

Example:

```python
class ModelClient:
    async def call(self, messages, tools=None):
        ...
```

Provider-specific behavior stays inside provider clients.

Never place provider-specific API logic inside:

```text
orchestrator.py
planner.py
api/messages.py
```

---

# 8. Memory Layer

Folder:

```text
backend/app/memory/
```

Recommended structure:

```text
memory/
├── memory_service.py
├── memory_router.py
├── recent_memory.py
├── summary_memory.py
├── profile_memory.py
├── workspace_memory.py
├── artifact_memory.py
└── tool_memory.py
```

## Responsibilities

### `memory_service.py`

Unified interface used by the harness.

### `memory_router.py`

Decides which memory categories are relevant.

### `recent_memory.py`

Recent conversation window.

### `summary_memory.py`

Long-thread summary retrieval/update.

### `profile_memory.py`

User-level stable preferences/facts.

### `workspace_memory.py`

Project/workspace facts and decisions.

### `artifact_memory.py`

Previous generated outputs and lineage.

### `tool_memory.py`

Important prior execution history.

Do not put vector DB implementation here unless it is explicitly semantic memory infrastructure. General document RAG belongs in `rag/`.

---

# 9. RAG Layer

Folder:

```text
backend/app/rag/
```

Recommended files:

```text
rag/
├── rag_service.py
├── ingestion_service.py
├── chunker.py
├── embeddings.py
├── retriever.py
├── vector_store.py
├── qdrant_store.py
├── atlas_vector_store.py
└── schemas.py
```

Only keep providers actually used.

## Responsibilities

### `ingestion_service.py`

Coordinates:

```text
file
→ extracted markdown
→ chunks
→ embeddings
→ vector index
```

### `chunker.py`

Markdown/text chunking only.

### `embeddings.py`

Embedding provider abstraction.

### `vector_store.py`

Base vector store interface.

### `qdrant_store.py`

Qdrant-specific implementation.

### `retriever.py`

Queries vector store, filters, ranks results.

### `rag_service.py`

Public application-facing RAG interface.

Do not put chat orchestration here.

---

# 10. Tool Layer

Folder:

```text
backend/app/tools/
```

Recommended structure:

```text
tools/
├── base.py
├── registry.py
├── orchestrator.py
├── schemas.py
├── search_documents.py
├── read_file.py
├── create_artifact.py
├── run_code.py
└── calculator.py
```

Only create tools actually needed.

## `base.py`

Tool protocol/interface.

## `registry.py`

Registers and finds available tools.

## `orchestrator.py`

Handles:

- tool lookup
- argument validation
- permission checks
- rate/quota checks
- tool-run creation
- execution routing
- structured results

## Individual tool files

One tool or tightly related tool family per file.

Do not create:

```text
all_tools.py
tools_helpers.py
tool_utils_everything.py
```

---

# 11. Sub-Agent Layer

Folder:

```text
backend/app/subagents/
```

Recommended structure:

```text
subagents/
├── base.py
├── manager.py
├── registry.py
├── planner_agent.py
├── requirements_agent.py
├── design_agent.py
├── code_agent.py
├── qa_agent.py
└── repair_agent.py
```

Only add agents needed by actual workflows.

## `base.py`

Common sub-agent interface.

## `manager.py`

Creates/executes sub-agent runs.

## `registry.py`

Maps names to available sub-agent definitions.

Each agent file contains:

- role
- system instructions
- allowed tools
- output schema
- limits

Do not let sub-agents directly own persistence or Docker execution.

---

# 12. Validation Layer

Folder:

```text
backend/app/validation/
```

Recommended files:

```text
validation/
├── base.py
├── validator_registry.py
├── tool_validator.py
├── artifact_validator.py
├── build_validator.py
├── schema_validator.py
├── rag_grounding_validator.py
└── response_validator.py
```

## Rule

Prefer deterministic validation when possible.

Examples:

```text
build_validator.py
    npm/build passed?

artifact_validator.py
    actual PDF/XLSX/DOCX valid?

schema_validator.py
    structured output matches schema?

rag_grounding_validator.py
    claims supported by retrieved context?
```

Do not hide validation inside prompts only.

---

# 13. Services Layer

Folder:

```text
backend/app/services/
```

Recommended files:

```text
services/
├── chat_service.py
├── run_service.py
├── file_service.py
├── artifact_service.py
├── job_service.py
├── permission_service.py
└── usage_service.py
```

Application/business logic belongs here.

Services may coordinate repositories/storage/queue, but should not implement the main AI orchestration loop.

---

# 14. Repository Layer

Folder:

```text
backend/app/repositories/
```

Recommended files:

```text
repositories/
├── user_repository.py
├── thread_repository.py
├── message_repository.py
├── run_repository.py
├── tool_run_repository.py
├── artifact_repository.py
├── file_repository.py
├── sandbox_job_repository.py
├── file_processing_job_repository.py
├── rag_index_job_repository.py
└── memory_repository.py
```

## Rule

Repository files contain persistence operations only.

Examples:

```python
get_by_id()
create()
update_status()
find_active()
append_block()
```

Do not put LLM reasoning, tool routing, or business rules in repositories.

---

# 15. Workers Layer

Folder:

```text
backend/app/workers/
```

Recommended files:

```text
workers/
├── sandbox_worker.py
├── file_processing_worker.py
├── rag_index_worker.py
├── cleanup_worker.py
└── recovery_worker.py
```

## `sandbox_worker.py`

```text
claim sandbox job
stage approved inputs
call sandbox-service
store artifacts
update job/tool-run state
```

## `file_processing_worker.py`

```text
claim file-processing job
read source file
extract markdown
store derived markdown
create RAG index job
```

## `rag_index_worker.py`

```text
claim RAG job
load markdown
chunk
embed
upsert vectors
update source index state
```

## `cleanup_worker.py`

```text
cleanup expired/orphaned temporary resources
```

## `recovery_worker.py`

```text
sweep expired leases
requeue or fail stale jobs
```

---

# 16. Storage Layer

Folder:

```text
backend/app/storage/
```

Recommended files:

```text
storage/
├── base.py
├── local_storage.py
├── s3_storage.py
└── paths.py
```

## `paths.py`

Centralize storage key construction.

Example:

```python
artifact_storage_key(...)
file_original_storage_key(...)
file_markdown_storage_key(...)
```

Do not scatter string path construction across the codebase.

---

# 17. Queue Layer

Folder:

```text
backend/app/queue/
```

Recommended files:

```text
queue/
├── base.py
├── redis_client.py
├── sandbox_queue.py
├── file_processing_queue.py
└── rag_index_queue.py
```

Queue files only handle dispatch/consume behavior.

MongoDB/database remains the durable source of job truth.

---

# 18. Models Layer

Folder:

```text
backend/app/models/
```

Recommended files:

```text
models/
├── user.py
├── workspace.py
├── thread.py
├── message.py
├── run.py
├── tool_run.py
├── file.py
├── artifact.py
├── sandbox_job.py
├── file_processing_job.py
├── rag_index_job.py
└── memory.py
```

One domain concept per file.

---

# 19. Schemas Layer

Folder:

```text
backend/app/schemas/
```

Recommended files:

```text
schemas/
├── chat.py
├── message.py
├── run.py
├── tool.py
├── file.py
├── artifact.py
├── job.py
└── rag.py
```

Use schemas for:

- API request models
- API response models
- internal structured model outputs where useful

Do not mix persistence models and external API contracts unnecessarily.

---

# 20. Core Layer

Folder:

```text
backend/app/core/
```

Recommended files:

```text
core/
├── config.py
├── logging.py
├── security.py
├── exceptions.py
└── constants.py
```

Avoid putting business logic here.

---

# 21. Utility Layer

Folder:

```text
backend/app/utils/
```

Only truly generic helpers belong here.

Examples:

```text
ids.py
time.py
hashing.py
mime.py
```

Do not turn `utils/` into a dumping ground.

If a helper is specific to RAG, keep it under `rag/`.

If specific to tools, keep it under `tools/`.

---

# 22. Sandbox Service Structure

The sandbox service must remain independent and narrow.

```text
sandbox-service/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── executions.py
│   │   └── health.py
│   ├── execution/
│   │   ├── docker_runner.py
│   │   ├── workspace.py
│   │   ├── limits.py
│   │   └── cleanup.py
│   ├── validation/
│   │   ├── output_validator.py
│   │   └── file_validator.py
│   ├── models/
│   │   ├── execution_request.py
│   │   └── execution_response.py
│   └── core/
│       ├── config.py
│       └── security.py
│
├── sandbox/
│   ├── Dockerfile
│   └── requirements.txt
│
└── tests/
```

The sandbox service must not contain:

```text
memory/
rag/
repositories/
MongoDB clients
R2/S3 clients
chat services
subagents/
orchestration/
```

Its contract is:

```text
code + approved input files + limits
→ isolated execution
→ validated outputs + logs
```

---

# 23. Infrastructure Structure

```text
infra/
├── docker/
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── sandbox-service.Dockerfile
│
├── compose/
│   ├── docker-compose.dev.yml
│   └── docker-compose.prod.yml
│
├── nginx/
│   └── nginx.conf
│
└── deployment/
    └── README.md
```

Do not mix application code into `infra/`.

---

# 24. Documentation Structure

```text
docs/
├── ARCHITECTURE.md
├── HARNESS.md
├── ORCHESTRATION.md
├── MEMORY.md
├── TOOLS.md
├── SUBAGENTS.md
├── VALIDATION.md
├── RAG.md
├── SANDBOX.md
├── ARTIFACTS.md
└── DEPLOYMENT.md
```

When structural decisions change, update relevant documentation.

---

# 25. Testing Structure

Prefer colocated unit tests or a clear backend test tree.

Example:

```text
backend/tests/
├── unit/
│   ├── harness/
│   ├── memory/
│   ├── tools/
│   ├── validation/
│   ├── repositories/
│   └── services/
│
├── integration/
│   ├── test_chat_flow.py
│   ├── test_tool_flow.py
│   ├── test_rag_flow.py
│   └── test_sandbox_flow.py
│
└── fixtures/
```

Top-level:

```text
tests/end_to_end/
├── test_simple_chat.py
├── test_file_generation.py
├── test_website_generation.py
└── test_multi_user_isolation.py
```

---

# 26. Naming Conventions

Use predictable suffixes:

```text
*_service.py
*_repository.py
*_worker.py
*_validator.py
*_client.py
*_manager.py
*_registry.py
*_orchestrator.py
*_adapter.py
```

Use nouns for domain models:

```text
artifact.py
run.py
message.py
```

Avoid:

```text
helpers.py
misc.py
utils2.py
manager_new.py
temp.py
old.py
new_version.py
final_final.py
```

---

# 27. Import Direction Rules

Maintain dependency direction.

Preferred direction:

```text
api
 ↓
services
 ↓
harness/application modules
 ↓
repositories/storage/queue/provider adapters
```

Harness may depend on:

```text
memory
rag
tools
subagents
validation
model_clients
services interfaces
```

Repositories must not depend on harness.

Sandbox-service must not depend on backend.

Frontend must not import backend implementation.

---

# 28. File Size and Responsibility Rule

A file becoming large is not automatically wrong.

Split a file when it has multiple responsibilities.

Warning signs:

- API route contains orchestration
- repository contains business rules
- orchestrator contains raw database queries
- tool file contains several unrelated tools
- one service handles files, artifacts, users, and jobs
- `utils.py` keeps growing
- one React component contains API logic, state, streaming, and rendering

Before splitting, identify the actual responsibility boundary.

---

# 29. New File Placement Decision Tree

When asked to create a new file, determine placement using this logic:

```text
Is it UI?
→ frontend/

Is it an HTTP endpoint?
→ backend/app/api/

Is it orchestration/workflow control?
→ backend/app/harness/

Is it an LLM provider adapter?
→ backend/app/model_clients/

Is it user/project/history memory?
→ backend/app/memory/

Is it document embedding/retrieval?
→ backend/app/rag/

Is it an action callable by an AI?
→ backend/app/tools/

Is it a specialist AI role?
→ backend/app/subagents/

Is it output correctness checking?
→ backend/app/validation/

Is it application/business logic?
→ backend/app/services/

Is it database persistence logic?
→ backend/app/repositories/

Is it background job execution?
→ backend/app/workers/

Is it object/file storage?
→ backend/app/storage/

Is it Redis/job dispatch?
→ backend/app/queue/

Is it a persistence/domain model?
→ backend/app/models/

Is it an API/input/output schema?
→ backend/app/schemas/

Is it shared configuration/security/logging?
→ backend/app/core/

Is it isolated code execution?
→ sandbox-service/
```

If none match, do not create a new folder immediately. Re-evaluate the responsibility.

---

# 30. Rules for Creating New Folders

Do not create a folder for a single trivial file unless:

- the concept is expected to grow
- the folder represents a strong architectural boundary
- consistency requires it

Good folder:

```text
validation/
```

because multiple validators will exist.

Weak folder:

```text
prompts/
```

containing one tiny string with no clear lifecycle.

Use judgment.

---

# 31. Rules for Moving Existing Files

Before moving any file:

1. identify its real responsibility
2. identify all imports/references
3. check tests
4. move file
5. update imports
6. update dependency injection/container registrations
7. update docs if architecture changes
8. run tests/build
9. verify no duplicate old file remains

Do not leave temporary compatibility duplicates unless explicitly required.

---

# 32. Rules for Renaming Files

Rename when:

- the existing name is vague
- the responsibility changed
- naming convention is inconsistent

Example:

```text
agent_manager.py
```

If it only manages sub-agents, prefer:

```text
subagent_manager.py
```

Do not rename files for cosmetic reasons if it creates unnecessary churn.

---

# 33. Rules for Refactoring Existing Structure

When reorganizing an existing codebase, use incremental checkpoints.

Preferred sequence:

```text
Checkpoint 1
- inspect repository
- produce current structure map
- identify misplacements
- no code changes

Checkpoint 2
- create target folders
- move low-risk files
- repair imports
- run tests

Checkpoint 3
- move orchestration/tool/memory boundaries
- repair DI/registries
- run tests

Checkpoint 4
- clean obsolete files
- update docs
- final validation
```

Do not move the whole repository blindly in one pass.

---

# 34. Structure Validation Checklist

After every structural change, verify:

```text
[ ] frontend contains no backend business logic
[ ] API routes remain thin
[ ] orchestrator contains control flow, not low-level implementations
[ ] provider clients are isolated
[ ] tools are individually discoverable
[ ] sub-agents are individually discoverable
[ ] validation is separate from execution
[ ] workers are separate from request handlers
[ ] repositories contain persistence only
[ ] sandbox-service has no DB/RAG/business dependencies
[ ] no duplicate old files remain
[ ] imports resolve
[ ] tests pass
[ ] build passes
[ ] docs reflect structure
```

---

# 35. Structure Anti-Patterns

Reject these patterns.

## Giant `agent.py`

Bad:

```text
agent.py
- prompt
- tools
- RAG
- DB
- Docker
- validation
- sub-agents
```

Split by responsibility.

## Giant `services.py`

Do not place every service into one file.

## `common/` dumping ground

If code has a domain, place it in the domain.

## Circular dependencies

Example to avoid:

```text
tools → harness → tools
```

Instead, define clean interfaces.

## Sandbox importing backend code

Avoid:

```python
from backend.app.repositories import ...
```

inside sandbox-service.

## Provider logic inside orchestration

Avoid:

```python
openai.ChatCompletion(...)
```

inside `orchestrator.py`.

---

# 36. Target End-to-End Request Path

The repository should make this path visually understandable:

```text
Frontend
    ↓
API route
    ↓
Chat/Run Service
    ↓
Run Orchestrator
    ↓
Context Builder
    ├── Memory Service
    ├── RAG Service
    └── Tool Registry
    ↓
Model Client
    ↓
Decision Engine
    ├── Tool Orchestrator
    │     ↓
    │   Worker / Tool
    │     ↓
    │   Sandbox if required
    │
    └── Sub-Agent Manager
          ↓
        Specialist Agent

Results
    ↓
Validation
    ↓
Feedback / Retry if needed
    ↓
Finalizer
    ↓
Message Repository
    ↓
Frontend Stream / Final UI
```

The file structure should make this request path easy to trace.

---

# 37. Example: Website Generation Placement

For a request:

```text
"Build me a professional business portfolio website."
```

Relevant files should align like:

```text
backend/app/harness/orchestrator.py
backend/app/harness/planner.py
backend/app/memory/memory_service.py
backend/app/subagents/design_agent.py
backend/app/subagents/code_agent.py
backend/app/subagents/qa_agent.py
backend/app/tools/create_artifact.py
backend/app/workers/sandbox_worker.py
backend/app/validation/build_validator.py
sandbox-service/app/execution/docker_runner.py
backend/app/services/artifact_service.py
frontend/src/components/artifacts/ArtifactCard.tsx
```

Do not place the whole website-generation workflow into:

```text
website_agent.py
```

unless that file is merely a thin domain workflow adapter.

---

# 38. Dependency Injection / Container Alignment

If the backend uses a DI container, register dependencies by domain.

Recommended conceptual alignment:

```text
Container
├── repositories
├── storage
├── queue
├── model clients
├── memory services
├── RAG services
├── tool registry
├── validators
├── sub-agent registry
├── planner
├── context builder
├── orchestrator
└── application services
```

Keep object construction outside domain implementation files where practical.

---

# 39. Prompts and Configuration

Do not scatter long prompts across random files.

If prompts become substantial, use:

```text
backend/app/prompts/
├── orchestration.py
├── planner.py
├── repair.py
└── subagents/
```

Only create this folder once prompts are large enough to justify it.

For small prompts, keep them near the component that owns them.

---

# 40. Events

If event types grow, use:

```text
backend/app/events/
├── types.py
├── publisher.py
└── schemas.py
```

Examples:

```text
run.created
model.streaming
tool.requested
tool.completed
artifact.created
validation.failed
run.completed
```

Do not create an events layer until the application actually uses events.

---

# 41. Artifact and File Separation

Keep:

```text
files
```

for user/uploaded source material.

Keep:

```text
artifacts
```

for AI-generated outputs.

Do not merge the concepts just because both are binary files.

Shared processing can use common services, but domain models remain distinct.

---

# 42. Temporary Files

Temporary runtime files must not live in source folders.

Use OS/runtime temporary paths such as:

```text
/tmp/ai-harness/
```

or configured runtime directories.

Never create:

```text
backend/temp/
backend/generated/
frontend/tmp/
```

for runtime data committed alongside source code.

---

# 43. Generated Code

Generated user artifacts are runtime data, not repository source.

They belong in:

```text
object storage
temporary execution workspace
artifact storage
```

not:

```text
backend/generated-websites/
```

---

# 44. Structural Change Output Format

Whenever this skill is used to make structural changes, the IDE agent must report:

```markdown
## Structure Changes

### Created
- path/to/new/file.py
- path/to/new/folder/

### Moved
- old/path.py → new/path.py

### Renamed
- old_name.py → new_name.py

### Deleted
- obsolete/path.py

### Import/Reference Updates
- module A
- module B

### Validation
- backend tests: pass/fail
- frontend build: pass/fail
- import check: pass/fail

### Remaining Structural Issues
- ...
```

Do not hide file moves.

---

# 45. Before Any Structural Change

The agent must first inspect:

```text
current folders
current file responsibilities
imports
tests
DI registrations
runtime entrypoints
Docker files
configuration references
```

Never assume the repository matches this skill exactly.

The existing repository is the source of truth for what currently exists.

This skill defines the target organization and placement rules.

---

# 46. Preserve Working Behavior

This skill is structural.

The agent must avoid changing behavior unless required to preserve imports or architectural boundaries.

If a move requires code edits:

- keep them minimal
- preserve signatures
- preserve API routes
- preserve config keys
- preserve database schema unless explicitly requested

Do not use a structural request as permission to redesign unrelated logic.

---

# 47. No Premature Abstraction

Do not create interfaces/providers/managers solely because this document lists them.

Create them when the actual project requires the abstraction.

Examples:

If only one vector provider exists and no provider abstraction is needed yet, a minimal:

```text
rag/vector_store.py
```

may be enough.

If multiple providers exist, split:

```text
rag/vector_store.py
rag/qdrant_store.py
rag/atlas_vector_store.py
```

The goal is clarity, not maximal file count.

---

# 48. No Empty Placeholder Files

Do not create dozens of empty files just to match the tree.

Only create files that:

- are immediately needed
- contain real interfaces/implementation
- establish a required architectural boundary

If a future component is not implemented, document it instead of creating empty source files.

---

# 49. Final Canonical Structure

Use this as the long-term reference:

```text
ai-harness/
│
├── frontend/
│   └── src/
│       ├── app/
│       ├── components/
│       │   ├── chat/
│       │   ├── artifacts/
│       │   ├── jobs/
│       │   ├── sources/
│       │   └── common/
│       ├── hooks/
│       ├── services/
│       ├── state/
│       ├── types/
│       └── utils/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── harness/
│   │   ├── model_clients/
│   │   ├── memory/
│   │   ├── rag/
│   │   ├── tools/
│   │   ├── subagents/
│   │   ├── validation/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── workers/
│   │   ├── storage/
│   │   ├── queue/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── core/
│   │   └── utils/
│   └── tests/
│
├── sandbox-service/
│   ├── app/
│   │   ├── api/
│   │   ├── execution/
│   │   ├── validation/
│   │   ├── models/
│   │   └── core/
│   ├── sandbox/
│   └── tests/
│
├── infra/
│   ├── docker/
│   ├── compose/
│   ├── nginx/
│   └── deployment/
│
├── docs/
├── scripts/
├── tests/
│   └── end_to_end/
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

# 50. Final Structural Principles

Always enforce these principles:

1. **One file should have one clear primary responsibility.**
2. **The orchestrator coordinates; it does not implement everything.**
3. **Tools perform actions; tool orchestration controls access to those actions.**
4. **Sub-agents reason within narrow roles.**
5. **Validators check outputs independently of generators.**
6. **Workers handle slow/background work.**
7. **Sandbox-service remains isolated from application persistence and business logic.**
8. **Repositories handle persistence only.**
9. **Services contain application/business behavior.**
10. **Frontend never becomes a second backend.**
11. **Vector search remains separate from general memory.**
12. **Generated runtime files never live in the source tree.**
13. **Do not create abstractions before they are needed.**
14. **Do not create empty placeholder source files.**
15. **After every structural refactor, update imports and run tests/build.**
16. **Keep naming explicit enough that a new engineer can locate functionality without searching the whole repository.**

---

# Skill Execution Checklist

When this skill is invoked, follow this exact sequence:

```text
1. Inspect current repository tree.
2. Identify the requested new/changed responsibility.
3. Determine its correct architectural layer.
4. Reuse an existing folder if the responsibility already has a home.
5. Create a new folder only if a real architectural boundary exists.
6. Choose an explicit filename using project naming conventions.
7. Check all imports/references before moving or renaming anything.
8. Make the smallest structural change that solves the problem.
9. Update imports, DI registrations, configs, and tests.
10. Remove obsolete duplicate files.
11. Run relevant unit/integration/build validation.
12. Report the exact structural changes made.
```

---

# Skill Boundaries

This skill should NOT independently:

- redesign product features
- rewrite business logic
- change database schemas
- change API contracts
- add new AI providers
- add new tools/sub-agents unless requested
- alter UI design
- modify deployment topology

unless those changes are explicitly required by the user's request.

The skill's job is:

> **Keep the AI harness repository structurally clean, predictable, scalable, and easy for both humans and AI coding agents to navigate.**
