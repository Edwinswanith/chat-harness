import asyncio
import time
from uuid import uuid4

from app.harness.run_state import transition_allowed
from app.harness.execution_events import envelope
from app.repositories.mongo_repository import MongoEntityRepository

TERMINAL = {"completed", "failed", "cancelled"}


class MongoRunRepository:
    def __init__(self, database, entities):
        self.database, self.entities = database, entities

    def _emit(self, run_id, event, data):
        run = self.database.assistant_runs.find_one({"_id": run_id}) or {"id": run_id}
        self.database.events.insert_one({"_id": uuid4().hex, "run_id": run_id, "event": event,
                                         "data": envelope(event, data, run), "created_at": time.time()})

    async def submit(self, scope, request, attachment_blocks=None):
        query = {"user_id": scope.user_id, "workspace_id": scope.workspace_id, "key": request.idempotency_key}
        existing = await asyncio.to_thread(self.database.request_keys.find_one, query)
        if existing:
            run = await self.entities.get("run", existing["run_id"], scope)
            if run["request"] != request.model_dump(mode="json"):
                raise ValueError("Idempotency key already used for a different request")
            return run
        request_data = request.model_dump(mode="json")
        run = MongoEntityRepository._document(scope, request.thread_id,
            {"status": "created", "request": request_data, "attempts": 0,
             "resolved_file_scope": request_data["file_scope"], "resolved_file_ids": request_data["file_ids"]})
        message = MongoEntityRepository._document(scope, request.thread_id,
            {"role": "user", "text": request.text, "run_id": run["id"], "blocks": attachment_blocks or [],
             "attached_file_ids": request_data["file_ids"], "file_scope": request_data["file_scope"]})
        assistant = MongoEntityRepository._document(scope, request.thread_id,
            {"role": "assistant", "text": "", "run_id": run["id"], "blocks": [], "status": "streaming"})
        run["assistant_message_id"] = assistant["id"]
        run["current_message_id"] = message["id"]
        def write():
            from pymongo.errors import DuplicateKeyError
            try:
                self.database.request_keys.insert_one(dict(query, _id=f"{scope.user_id}:{scope.workspace_id}:{request.idempotency_key}", run_id=run["id"]))
            except DuplicateKeyError:
                return None
            self.database.assistant_runs.insert_one(dict(run, _id=run["id"]))
            self.database.chat_messages.insert_one(dict(message, _id=message["id"]))
            self.database.chat_messages.insert_one(dict(assistant, _id=assistant["id"]))
            self.database.chat_threads.update_one({"_id": request.thread_id, "user_id": scope.user_id,
                "workspace_id": scope.workspace_id}, {"$set": {"last_message_at": time.time(), "updated_at": time.time(),
                "preview": request.text[:160], "title": request.text[:72]}, "$inc": {"message_count": 2}})
            self._emit(run["id"], "state", {"status": "created"})
            return run
        result = await asyncio.to_thread(write)
        if result:
            return result
        return await self.submit(scope, request, attachment_blocks)

    async def claim(self, run_id, scope):
        def write():
            result = self.database.assistant_runs.find_one_and_update(
                {"_id": run_id, "user_id": scope.user_id, "workspace_id": scope.workspace_id, "status": "created"},
                {"$set": {"status": "planning", "updated_at": time.time()}}, projection={"_id": 0})
            if result:
                self._emit(run_id, "state", {"status": "planning"})
            return bool(result)
        return await asyncio.to_thread(write)

    async def transition(self, run_id, scope, status, **changes):
        run = await self.entities.get("run", run_id, scope)
        if run["status"] in TERMINAL:
            return run
        if not transition_allowed(run["status"], status):
            raise ValueError(f"Invalid run transition: {run['status']} -> {status}")
        changes.update(status=status, updated_at=time.time())
        await asyncio.to_thread(self.database.assistant_runs.update_one, {"_id": run_id}, {"$set": changes})
        self._emit(run_id, "state", {"status": status, **{k: v for k, v in changes.items() if k != "updated_at"}})
        return await self.entities.get("run", run_id, scope)

    async def event(self, run_id, event, data):
        await asyncio.to_thread(self._emit, run_id, event, data)

    async def append_delta(self, run_id, scope, text):
        run = await self.entities.get("run", run_id, scope)
        message = await self.entities.get("message", run["assistant_message_id"], scope)
        updated = message["text"] + text
        await self.entities.patch("message", message["id"], scope, text=updated, status="streaming")
        await self.event(run_id, "delta", {"text": text, "full_text": updated, "message_id": message["id"]})

    async def events(self, run_id, after=0):
        def read():
            rows = list(self.database.events.find({"run_id": run_id}, {"_id": 0}).sort("created_at", 1))
            return [dict(row, seq=index + 1) for index, row in enumerate(rows) if index + 1 > after]
        return await asyncio.to_thread(read)

    async def finish(self, run_id, scope, text, blocks):
        run = await self.entities.get("run", run_id, scope)
        if run["status"] in TERMINAL:
            return run
        message = await self.entities.patch("message", run["assistant_message_id"], scope, text=text,
                                            blocks=blocks, status="completed")
        await asyncio.to_thread(self.database.assistant_runs.update_one, {"_id": run_id},
                                 {"$set": {"status": "completed", "message_id": message["id"], "updated_at": time.time()}})
        await self.event(run_id, "state", {"status": "completed"})
        await self.event(run_id, "final", {"message": message})
        return await self.entities.get("run", run_id, scope)

    async def recover(self):
        def write():
            for collection in (self.database.assistant_runs, self.database.sandbox_jobs, self.database.tool_runs):
                collection.update_many({"status": {"$nin": list(TERMINAL | {"success", "error", "indexed"})}},
                    {"$set": {"status": "failed", "error": "Server restarted; submit a new request to retry.", "updated_at": time.time()}})
        await asyncio.to_thread(write)
