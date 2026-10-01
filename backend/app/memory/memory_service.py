from app.schemas.contracts import MemoryBundle


class MemoryRouter:
    def categories(self, query):
        return ("recent", "summary")


class MemoryService:
    def __init__(self, repo, window=12):
        self.repo, self.window, self.router = repo, window, MemoryRouter()

    async def retrieve_for_request(self, scope, thread_id, query):
        self.router.categories(query)
        messages = await self.repo.list("message", scope, thread_id)
        # Bounded extractive summary; recent corrections remain last in context.
        older = messages[:-self.window]
        summary = "\n".join(f"{m['role']}: {m['text'][:160]}" for m in older[-20:])
        summaries = await self.repo.list("conversation_summary", scope, thread_id)
        if summaries:
            await self.repo.patch("conversation_summary", summaries[0]["id"], scope,
                                  summary=summary, covered_until_message_id=older[-1]["id"] if older else None,
                                  version=summaries[0].get("version", 0) + 1)
        elif summary:
            await self.repo.create("conversation_summary", scope, thread_id, summary=summary,
                                   covered_until_message_id=older[-1]["id"] if older else None, version=1)
        return MemoryBundle(recent=messages[-self.window:], summary=summary, records_found=len(messages))
