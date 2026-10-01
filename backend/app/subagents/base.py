from app.schemas.contracts import SubAgentResult


class ReviewerAgent:
    name = "reviewer"

    async def run(self, model, run, feedback):
        text = await model.review(f"Request: {run['request']['text']}\nValidation failure: {feedback}")
        return SubAgentResult(feedback=text)
