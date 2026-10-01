# Sandbox Skill

## Purpose
Execute untrusted AI-generated code in isolated disposable environments.

## Contract
Input:
- code
- approved files
- limits

Output:
- stdout/stderr
- exit status
- validated output files

## Security
- one job = one container
- network off by default
- non-root
- read-only root
- drop capabilities
- no-new-privileges
- CPU/RAM/PID/time limits
- no Docker socket inside execution container
- no DB/storage/LLM secrets
- cleanup always

## Boundary
Sandbox does not own:
- users
- MongoDB
- RAG
- chat state
- artifacts metadata
