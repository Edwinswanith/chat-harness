# Result & Output Skill

## Purpose
Finalize user-visible answers, artifacts, statuses, and source references.

## Outputs
- final text response
- artifacts
- source references
- run status
- clear error state

## Finalization Flow
```text
validated result
→ store artifact metadata
→ attach message blocks
→ mark run completed
→ emit final event
→ frontend renders
```

## Rules
- never claim file exists unless artifact record exists
- never claim success before validation
- output format must be consistent
- preserve artifact IDs and lineage
