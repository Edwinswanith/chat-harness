# Feedback Loop Skill

## Purpose
Repair failed or weak outputs through controlled validation feedback.

## Flow
```text
generate
→ execute
→ validate
→ if pass: accept
→ if fail: classify
→ build feedback
→ repair/retry
→ validate again
→ stop at max attempts
```

## Feedback Types
- execution error
- build error
- artifact validation failure
- schema failure
- grounding failure
- user correction

## Rules
- feedback must be specific and actionable
- do not dump huge raw logs directly to model
- retry only retryable failures
- enforce max attempts/time/cost
- preserve previous artifact versions
