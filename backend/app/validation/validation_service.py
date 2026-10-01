from app.schemas.contracts import ValidationResult


class ValidationService:
    async def tool(self, result):
        return ValidationResult(passed=result.status == "success", retryable=result.retryable,
                                feedback=result.error, errors=[result.error] if result.error else [])

    async def response(self, text):
        return ValidationResult(passed=bool(text.strip()), retryable=True,
                                feedback="Return a nonempty final answer.")
