# Harness Skill

## Purpose
Combine orchestration, context, memory, tools, sub-agents, validation, and model clients into one controlled AI worker environment.

## Core Components
```text
RunOrchestrator
Planner
ContextBuilder
ModelClient
MemoryService
RagService
ToolOrchestrator
SubAgentManager
ValidationService
Finalizer
```

## Core Loop
```text
request
→ context
→ model
→ direct/tool/subagent
→ result
→ validate
→ feedback
→ final
```

## Rules
- model is not the system
- harness controls model access to capabilities
- deterministic checks preferred over LLM judgment
- all actions observable and bounded
