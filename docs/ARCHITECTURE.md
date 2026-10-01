# Architecture

The API derives its user/workspace scope from a static Bearer token. Routes delegate to services, which use repositories for SQLite persistence. `RunOrchestrator` coordinates planning, memory, RAG, Gemini, tools, reviewer feedback, validation, and finalization without direct storage or Docker calls.

The backend runs on the host. `sandbox-service` is a separate Docker service. It creates one short-lived runner container per artifact job with network disabled, a read-only filesystem, dropped capabilities, no-new-privileges, resource limits, and no mounted Docker socket. The Docker socket is available only to the sandbox service container so it can create runners.

SQLite and local storage are durable sources of truth. RAG vectors are stored in SQLite and can be rebuilt from derived Markdown. No source, artifact, run, or vector lookup crosses the authenticated user/workspace boundary.
