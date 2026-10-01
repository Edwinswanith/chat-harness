from app.schemas.contracts import Decision


class MockModelClient:
    """Deterministic offline model; replace through the ModelClient interface."""

    async def call(self, context):
        if context.results:
            result = context.results[-1]
            if result.status == "success":
                if result.artifact_ids:
                    return Decision(kind="final", text="Your report is ready. Download it below.")
                return Decision(kind="final", text=f"Result: {result.data.get('value', result.data)}")
            return Decision(kind="final", text=f"Unable to complete the request: {result.error}")
        text = context.request["text"]
        if text.lower().startswith("calculate "):
            return Decision(kind="tool", name="calculator", arguments={"expression": text[10:]})
        if any(word in text.lower() for word in ("report", "artifact", "file")):
            source = "\n\n".join(chunk["text"] for chunk in context.rag.chunks)
            return Decision(kind="tool", name="create_artifact", arguments={
                "name": "report.md", "content": "# Simple report\n\n" + (source or text),
                "source_ids": context.request.get("file_ids", [])})
        return Decision(kind="final", text="Mock assistant: " + text)
