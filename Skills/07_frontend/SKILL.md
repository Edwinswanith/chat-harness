# Frontend Skill

## Purpose
Build the chatbot UI and show streaming status, jobs, sources, and artifacts.

## Responsibilities
- composer/input
- message rendering
- streaming updates
- job progress
- artifact cards/downloads
- source/index status
- retry/cancel controls

## Must Not Own
- orchestration
- permissions truth
- RAG implementation
- DB logic
- sandbox logic

## Structure
```text
components/chat/
components/jobs/
components/artifacts/
hooks/
services/
state/
types/
```

## Flow
```text
user action
→ frontend API service
→ backend
→ stream/SSE events
→ update local store
→ render final state
```
