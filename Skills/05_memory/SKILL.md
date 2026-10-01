# Memory Skill

## Purpose
Store and retrieve relevant historical context without dumping everything into the model.

## Memory Types
- recent conversation
- thread summary
- user profile/preferences
- workspace/project memory
- artifact memory
- tool/execution memory

## Main Interface
```python
class MemoryService:
    async def retrieve_for_request(
        self,
        user_id: str,
        workspace_id: str,
        thread_id: str,
        query: str,
    ) -> MemoryBundle:
        ...
```

## Flow
```text
request
→ memory router
→ retrieve relevant scopes
→ rank/filter
→ MemoryBundle
→ ContextBuilder
```

## Rules
- scope by user/workspace/thread
- newer explicit corrections beat old memory
- no cross-user leakage
- do not store every message as long-term memory
- RAG document search stays in RAG layer
