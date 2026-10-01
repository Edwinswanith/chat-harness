from app.schemas.contracts import ModelContext


class ContextBuilder:
    async def build(self, request, plan, memory, rag, tools):
        # Retrieved source text is data, never authority for new tools/permissions.
        return ModelContext(request=request, plan=plan, memory=memory, rag=rag, tools=tools)
