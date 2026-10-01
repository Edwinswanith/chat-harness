import asyncio
import time


class ChatService:
    def __init__(self, repo, runs, files):
        self.repo, self.runs, self.files = repo, runs, files
        self.orchestrator = None
        self.tasks = {}

    async def create_thread(self, scope, mode="chatbot", project_workspace_id=None):
        conversation = await self.repo.create("thread", scope, "", title="New conversation",
            conversation_id="", mode=mode, project_workspace_id=project_workspace_id, status="active", message_count=0, memory={"scope": "conversation"},
            last_message_at=time.time(), preview="")
        return await self.repo.patch("thread", conversation["id"], scope, conversation_id=conversation["id"])

    async def conversations(self, scope, mode=None, project_workspace_id=None):
        records = await self.repo.list("thread", scope)
        active = [item for item in records if item.get("status", "active") == "active" and
                  (mode is None or item.get("mode", "chatbot") == mode) and
                  (project_workspace_id is None or item.get("project_workspace_id") == project_workspace_id)]
        return sorted(active, key=lambda item: item.get("last_message_at", item.get("updated_at", 0)), reverse=True)

    async def conversation(self, scope, conversation_id):
        return await self.repo.get("thread", conversation_id, scope)

    async def messages(self, scope, thread_id):
        await self.repo.get("thread", thread_id, scope)
        messages = await self.repo.list("message", scope, thread_id)
        runs = {run["id"]: run for run in await self.repo.list("run", scope, thread_id)}
        for message in messages:
            run = runs.get(message.get("run_id"))
            if message.get("role") == "assistant" and message.get("status") == "streaming" and run and run.get("status") in {"completed", "failed", "cancelled"}:
                text = message.get("text") or ("The workspace task was interrupted. Send “continue” to resume from the existing files." if run.get("mode") == "workspace" else "The response was interrupted. Please resend the request.")
                message = await self.repo.patch("message", message["id"], scope, text=text, status=run["status"])
        return await self.repo.list("message", scope, thread_id)

    async def paged_messages(self, scope, conversation_id, cursor=None, limit=100):
        messages = await self.messages(scope, conversation_id)
        start = next((index + 1 for index, item in enumerate(messages) if item["id"] == cursor), 0) if cursor else 0
        items = messages[start:start + limit]
        return {"items": items, "next_cursor": items[-1]["id"] if len(items) == limit else None}

    async def update_conversation(self, scope, conversation_id, title=None, status=None):
        await self.conversation(scope, conversation_id)
        changes = {"updated_at": time.time()}
        if title is not None:
            changes["title"] = title.strip()[:120] or "New conversation"
        if status is not None:
            changes["status"] = status
        return await self.repo.patch("thread", conversation_id, scope, **changes)

    async def active_run(self, scope, conversation_id):
        runs = await self.repo.list("run", scope, conversation_id)
        active = [run for run in runs if run.get("status") not in {"completed", "failed", "cancelled"}]
        return active[-1] if active else None

    async def submit(self, scope, request):
        await self.repo.get("thread", request.thread_id, scope)
        available = await self.files.list(scope, request.thread_id)
        file_scope, file_ids = self._resolve_file_scope(request.text, request.file_ids, available)
        request = request.model_copy(update={"file_ids": file_ids, "file_scope": file_scope})
        blocks = []
        for file_id in request.file_ids:
            source = await self.files.get_source(file_id, scope, request.thread_id)
            blocks.append({"type": "source", "id": source["id"], "name": source["name"], "status": source["status"]})
        conversation = await self.conversation(scope, request.thread_id)
        run = await self.runs.submit(scope, request, blocks)
        if run["status"] == "created":
            run = await self.repo.patch("run", run["id"], scope, mode=conversation.get("mode", "chatbot"),
                                        project_workspace_id=conversation.get("project_workspace_id"))
        if run["status"] == "created" and run["id"] not in self.tasks:
            task = asyncio.create_task(self.orchestrator.run(run["id"], scope))
            self.tasks[run["id"]] = task
            task.add_done_callback(lambda _: self.tasks.pop(run["id"], None))
        return run

    @staticmethod
    def _resolve_file_scope(text, current_file_ids, available):
        """Old thread files require an explicit filename or an all-files request."""
        current = list(dict.fromkeys(current_file_ids))
        allowed = {source["id"] for source in available if source.get("status") != "failed"}
        if current:
            return "current_message", [source_id for source_id in current if source_id in allowed]
        prompt = text.lower()
        if any(phrase in prompt for phrase in ("all uploaded files", "all uploaded documents", "use all files", "use all documents")):
            return "thread", [source["id"] for source in available if source.get("status") != "failed"]
        selected = []
        for source in available:
            stem = source["name"].rsplit(".", 1)[0].lower().replace("-", " ").replace("_", " ")
            words = [word for word in stem.split() if len(word) > 2]
            if words and all(word in prompt for word in words):
                selected.append(source["id"])
        return ("explicit_selected", selected) if selected else ("current_message", [])

    async def cancel(self, scope, run_id):
        await self.repo.get("run", run_id, scope)
        task = self.tasks.get(run_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return await self.runs.transition(run_id, scope, "cancelled")

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
