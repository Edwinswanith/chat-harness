import json
import math
from uuid import uuid4


class SqliteVectorStore:
    def __init__(self, database):
        self.db = database

    async def replace_source(self, scope, source_id, thread_id, rows):
        def write(db):
            db.execute("DELETE FROM vectors WHERE user_id=? AND workspace_id=? AND source_id=?",
                       (scope.user_id, scope.workspace_id, source_id))
            for text, embedding in rows:
                db.execute("INSERT INTO vectors VALUES (?,?,?,?,?,?,?,strftime('%s','now'))",
                           (uuid4().hex, scope.user_id, scope.workspace_id, source_id, thread_id,
                            text, json.dumps(embedding)))
        await self.db.call(write)

    async def search(self, scope, query_embedding, source_ids, limit=5):
        def read(db):
            sql = "SELECT source_id,text,embedding FROM vectors WHERE user_id=? AND workspace_id=?"
            args = [scope.user_id, scope.workspace_id]
            if source_ids:
                sql += " AND source_id IN (" + ",".join("?" * len(source_ids)) + ")"
                args.extend(source_ids)
            return [dict(row) for row in db.execute(sql, args)]
        rows = await self.db.call(read)
        def cosine(values):
            dot = sum(a * b for a, b in zip(query_embedding, values))
            scale = math.sqrt(sum(a * a for a in query_embedding) * sum(b * b for b in values))
            return dot / scale if scale else 0
        return [{"source_id": row["source_id"], "text": row["text"], "score": cosine(json.loads(row["embedding"]))}
                for row in sorted(rows, key=lambda r: cosine(json.loads(r["embedding"])), reverse=True)[:limit]]
