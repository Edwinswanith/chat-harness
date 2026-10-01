# API Skill

## Purpose
Define thin, typed, authenticated HTTP/SSE/WebSocket boundaries.

## Rules
API routes:
- validate input
- resolve auth
- call service
- map exceptions to responses
- stream events

API routes do not:
- run orchestration loops
- query DB directly
- execute Docker
- call vector store directly

## Naming
```text
/api/chats
/api/messages
/api/runs
/api/files
/api/artifacts
/api/jobs
/api/rag
```

## Contracts
Use request/response schemas and stable error codes.
