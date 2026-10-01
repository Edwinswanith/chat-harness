# Sub-Agent Skill

## Purpose
Create controlled specialist AI workers for complex subtasks.

## Use When
- task has distinct specialist domains
- independent work can run in parallel
- review/repair benefits from a separate role

## Do Not Use When
A single model/tool call is enough.

## Components
```text
SubAgentRegistry
SubAgentManager
BaseSubAgent
specialist agent definitions
SubAgentRun persistence
```

## SubAgent Definition
```python
class SubAgentDefinition:
    name: str
    role: str
    system_prompt: str
    allowed_tools: list[str]
    output_schema: type
    max_tool_calls: int
```

## Flow
```text
orchestrator identifies subtask
→ registry selects specialist
→ manager builds scoped context
→ sub-agent runs
→ structured result
→ result returns to orchestrator
```

## Rules
- orchestrator owns final decision
- sub-agent gets minimum context/tools
- no unlimited recursive spawning
- default max depth 1
- output must be typed/structured
