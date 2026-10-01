# Validation Skill

## Purpose
Check whether outputs actually satisfy technical and task requirements.

## Validators
- tool result validator
- schema validator
- artifact validator
- build validator
- RAG grounding validator
- response validator

## ValidationResult
```python
class ValidationResult(BaseModel):
    passed: bool
    retryable: bool = False
    errors: list[str] = []
    warnings: list[str] = []
    feedback: str | None = None
```

## Rules
- deterministic first
- validation separate from generator
- failed validation must not be presented as success
- validator output feeds feedback loop
