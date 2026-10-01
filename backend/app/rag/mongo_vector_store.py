import asyncio
import math
from uuid import uuid4


class MongoVectorStore:
    """Scoped, rebuildable embeddings index stored separately from application records."""

    def __init__(self, database):
        self.collection = database.rag_chunks

    async def replace_source(self, scope, source_id, thread_id, rows):
        documents = [{"_id": uuid4().hex, "user_id": scope.user_id, "workspace_id": scope.workspace_id,
                      "thread_id": thread_id, "source_id": source_id, "text": text, "embedding": embedding}
                     for text, embedding in rows]
        def write():
            self.collection.delete_many({"user_id": scope.user_id, "workspace_id": scope.workspace_id,
                                         "source_id": source_id})
            if documents:
                self.collection.insert_many(documents)
        await asyncio.to_thread(write)

    async def search(self, scope, query_embedding, source_ids, limit=5):
        query = {"user_id": scope.user_id, "workspace_id": scope.workspace_id}
        if source_ids:
            query["source_id"] = {"$in": source_ids}
        def read():
            return list(self.collection.find(query, {"_id": 0, "source_id": 1, "text": 1, "embedding": 1}))
        rows = await asyncio.to_thread(read)
        def cosine(values):
            dot = sum(a * b for a, b in zip(query_embedding, values))
            scale = math.sqrt(sum(a * a for a in query_embedding) * sum(b * b for b in values))
            return dot / scale if scale else 0
        return [{"source_id": row["source_id"], "text": row["text"], "score": cosine(row["embedding"])}
                for row in sorted(rows, key=lambda row: cosine(row["embedding"]), reverse=True)[:limit]]
