# Backend Skill

## Purpose
Own authenticated application state, services, persistence, orchestration wiring, queues, and artifact metadata.

## Responsibilities
- API boundary
- auth/permissions
- chat/thread/run state
- orchestration
- tools
- memory/RAG
- workers
- storage metadata
- queue coordination

## Rules
- API routes thin
- repositories persistence-only
- services business/application logic
- workers for slow tasks
- sandbox-service stays independent
