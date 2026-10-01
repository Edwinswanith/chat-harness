import asyncio
import time
from uuid import uuid4


COLLECTIONS = {
    "thread": "chat_threads", "message": "chat_messages", "run": "assistant_runs",
    "tool_run": "tool_runs", "file": "files", "artifact": "artifacts",
    "job": "sandbox_jobs", "memory": "memory_records",
    "conversation_summary": "conversation_summaries",
    "workspace": "workspaces", "workspace_session": "workspace_sessions",
    "workspace_file": "workspace_files", "workspace_change": "workspace_changes",
}


class MongoEntityRepository:
    """Mongo-backed structured records, preserving the existing scoped repository contract."""

    def __init__(self, database):
        self.database = database

    def collection(self, kind, body=None):
        if kind == "job":
            job_kind = (body or {}).get("kind")
            return self.database["file_processing_jobs" if job_kind == "ingestion" else "sandbox_jobs"]
        return self.database[COLLECTIONS.get(kind, kind)]

    def collections(self, kind):
        return ([self.database["sandbox_jobs"], self.database["file_processing_jobs"], self.database["rag_index_jobs"]]
                if kind == "job" else [self.collection(kind)])

    @staticmethod
    def _document(scope, thread_id, body):
        now = time.time()
        return dict(body, id=body.get("id", uuid4().hex), user_id=scope.user_id,
                    workspace_id=scope.workspace_id, thread_id=thread_id,
                    conversation_id=body.get("conversation_id", thread_id),
                    created_at=now, updated_at=now)

    async def create(self, record_kind, scope, thread_id, **body):
        item = self._document(scope, thread_id, body)
        await asyncio.to_thread(self.collection(record_kind, body).insert_one, dict(item, _id=item["id"]))
        return item

    async def get(self, kind, item_id, scope):
        query = {"_id": item_id, "user_id": scope.user_id, "workspace_id": scope.workspace_id}
        item = None
        for collection in self.collections(kind):
            item = await asyncio.to_thread(collection.find_one, query, {"_id": 0})
            if item:
                break
        if not item:
            raise KeyError("Resource not found")
        return item

    async def list(self, kind, scope, thread_id=None):
        query = {"user_id": scope.user_id, "workspace_id": scope.workspace_id}
        if thread_id is not None:
            query["thread_id"] = thread_id
        def read():
            return sorted((item for collection in self.collections(kind)
                           for item in collection.find(query, {"_id": 0})), key=lambda item: item["created_at"])
        return await asyncio.to_thread(read)

    async def patch(self, kind, item_id, scope, **changes):
        changes["updated_at"] = time.time()
        def write():
            from pymongo import ReturnDocument
            query = {"_id": item_id, "user_id": scope.user_id, "workspace_id": scope.workspace_id}
            for collection in self.collections(kind):
                item = collection.find_one_and_update(query, {"$set": changes},
                    return_document=ReturnDocument.AFTER, projection={"_id": 0})
                if item:
                    return item
            return None
        item = await asyncio.to_thread(write)
        if not item:
            raise KeyError("Resource not found")
        return item


def ensure_indexes(database):
    """Create only query and uniqueness indexes used by the harness."""
    database.request_keys.create_index([("user_id", 1), ("workspace_id", 1), ("key", 1)], unique=True)
    database.events.create_index([("run_id", 1), ("seq", 1)])
    database.chat_threads.create_index([("user_id", 1), ("last_message_at", -1)])
    database.chat_threads.create_index([("workspace_id", 1), ("updated_at", -1)])
    database.chat_messages.create_index([("conversation_id", 1), ("created_at", 1)])
    database.assistant_runs.create_index([("workspace_id", 1), ("created_at", -1)])
    database.files.create_index([("workspace_id", 1), ("thread_id", 1), ("created_at", -1)])
    database.artifacts.create_index([("workspace_id", 1), ("thread_id", 1), ("created_at", -1)])
    database.sandbox_jobs.create_index([("status", 1), ("created_at", 1)])
    database.file_processing_jobs.create_index([("status", 1), ("created_at", 1)])
    database.rag_index_jobs.create_index([("status", 1), ("created_at", 1)])
    database.memory_records.create_index([("workspace_id", 1), ("thread_id", 1), ("updated_at", -1)])
    database.memory_records.create_index([("user_id", 1), ("conversation_id", 1)])
    database.conversation_summaries.create_index([("conversation_id", 1)], unique=True)
    database.rag_chunks.create_index([("user_id", 1), ("workspace_id", 1), ("source_id", 1)])
    database.workspaces.create_index([("user_id", 1), ("updated_at", -1)])
    database.workspace_files.create_index([("user_id", 1), ("project_workspace_id", 1), ("relative_path", 1)], unique=True)
