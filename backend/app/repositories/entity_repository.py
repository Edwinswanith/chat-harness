import json
from app.repositories.database import Database


class EntityRepository:
    def __init__(self, database):
        self.db = database

    async def create(self, record_kind, scope, thread_id, **body):
        return await self.db.call(lambda db: Database.insert(db, record_kind, scope, thread_id, body))

    async def get(self, kind, item_id, scope):
        def read(db):
            row = db.execute("SELECT body FROM records WHERE kind=? AND id=? AND user_id=? AND workspace_id=?",
                             (kind, item_id, scope.user_id, scope.workspace_id)).fetchone()
            if not row:
                raise KeyError("Resource not found")
            return json.loads(row["body"])
        return await self.db.call(read)

    async def list(self, kind, scope, thread_id=None):
        def read(db):
            sql = "SELECT body FROM records WHERE kind=? AND user_id=? AND workspace_id=?"
            args = [kind, scope.user_id, scope.workspace_id]
            if thread_id is not None:
                sql += " AND thread_id=?"
                args.append(thread_id)
            return [json.loads(row["body"]) for row in db.execute(sql + " ORDER BY created", args)]
        return await self.db.call(read)

    async def patch(self, kind, item_id, scope, **changes):
        def write(db):
            row = db.execute("SELECT body FROM records WHERE kind=? AND id=? AND user_id=? AND workspace_id=?",
                             (kind, item_id, scope.user_id, scope.workspace_id)).fetchone()
            if not row:
                raise KeyError("Resource not found")
            item = dict(json.loads(row["body"]), **changes)
            Database.update(db, item)
            return item
        return await self.db.call(write)
