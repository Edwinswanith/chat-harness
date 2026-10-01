import json
import time
from app.repositories.database import Database
from app.harness.run_state import transition_allowed
from app.harness.execution_events import envelope


TERMINAL = {"completed", "failed", "cancelled"}


class RunRepository:
    def __init__(self, database, entities):
        self.db, self.entities = database, entities

    async def submit(self, scope, request, attachment_blocks=None):
        def write(db):
            row = db.execute("SELECT run_id FROM request_keys WHERE user_id=? AND workspace_id=? AND key=?",
                             (scope.user_id, scope.workspace_id, request.idempotency_key)).fetchone()
            if row:
                existing = json.loads(db.execute("SELECT body FROM records WHERE id=?", (row[0],)).fetchone()[0])
                if existing["request"] != request.model_dump(mode="json"):
                    raise ValueError("Idempotency key already used for a different request")
                return existing
            request_data = request.model_dump(mode="json")
            run = Database.insert(db, "run", scope, request.thread_id,
                                  {"status": "created", "request": request_data, "attempts": 0,
                                   "resolved_file_scope": request_data["file_scope"], "resolved_file_ids": request_data["file_ids"]})
            user_message = Database.insert(db, "message", scope, request.thread_id,
                {"role": "user", "text": request.text, "run_id": run["id"], "blocks": attachment_blocks or [],
                 "attached_file_ids": request_data["file_ids"], "file_scope": request_data["file_scope"]})
            assistant = Database.insert(db, "message", scope, request.thread_id,
                {"role": "assistant", "text": "", "run_id": run["id"], "blocks": [], "status": "streaming"})
            run["assistant_message_id"] = assistant["id"]
            run["current_message_id"] = user_message["id"]
            Database.update(db, run)
            thread_row = db.execute("SELECT body FROM records WHERE kind='thread' AND id=?", (request.thread_id,)).fetchone()
            if thread_row:
                thread = json.loads(thread_row["body"])
                thread.update(last_message_at=time.time(), updated_at=time.time(),
                              message_count=thread.get("message_count", 0) + 2,
                              preview=request.text[:160], title=request.text[:72] if thread.get("title") in {"", "New conversation", None} else thread["title"])
                Database.update(db, thread)
            db.execute("INSERT INTO request_keys VALUES (?,?,?,?)",
                       (scope.user_id, scope.workspace_id, request.idempotency_key, run["id"]))
            self.emit(db, run["id"], "state", {"status": "created"})
            return run
        return await self.db.call(write)

    @staticmethod
    def emit(db, run_id, event, data):
        row = db.execute("SELECT body FROM records WHERE id=? AND kind='run'", (run_id,)).fetchone()
        run = json.loads(row[0]) if row else {"id": run_id}
        db.execute("INSERT INTO events(run_id,body) VALUES (?,?)", (run_id, json.dumps({"event": event, "data": envelope(event, data, run)})))

    async def claim(self, run_id, scope):
        def write(db):
            row = db.execute("SELECT body FROM records WHERE id=? AND kind='run' AND user_id=? AND workspace_id=?",
                             (run_id, scope.user_id, scope.workspace_id)).fetchone()
            if not row:
                return False
            run = json.loads(row[0])
            if run["status"] != "created":
                return False
            run["status"] = "planning"
            Database.update(db, run)
            self.emit(db, run_id, "state", {"status": "planning"})
            return True
        return await self.db.call(write)

    async def transition(self, run_id, scope, status, **changes):
        def write(db):
            row = db.execute("SELECT body FROM records WHERE id=? AND user_id=? AND workspace_id=?",
                             (run_id, scope.user_id, scope.workspace_id)).fetchone()
            run = json.loads(row[0])
            if run["status"] in TERMINAL:
                return run
            if not transition_allowed(run["status"], status):
                raise ValueError(f"Invalid run transition: {run['status']} -> {status}")
            run.update(changes, status=status)
            Database.update(db, run)
            self.emit(db, run_id, "state", {"status": status, **changes})
            return run
        return await self.db.call(write)

    async def event(self, run_id, event, data):
        await self.db.call(lambda db: self.emit(db, run_id, event, data))

    async def append_delta(self, run_id, scope, text):
        def write(db):
            row = db.execute("SELECT body FROM records WHERE id=? AND user_id=? AND workspace_id=?", (run_id, scope.user_id, scope.workspace_id)).fetchone()
            run = json.loads(row["body"])
            message_row = db.execute("SELECT body FROM records WHERE id=?", (run["assistant_message_id"],)).fetchone()
            message = json.loads(message_row["body"])
            message["text"] += text
            Database.update(db, message)
            self.emit(db, run_id, "delta", {"text": text, "full_text": message["text"], "message_id": message["id"]})
        await self.db.call(write)

    async def events(self, run_id, after=0):
        return await self.db.call(lambda db: [dict(json.loads(row["body"]), seq=row["seq"])
            for row in db.execute("SELECT seq,body FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after))])

    async def finish(self, run_id, scope, text, blocks):
        def write(db):
            run = json.loads(db.execute("SELECT body FROM records WHERE id=? AND user_id=? AND workspace_id=?",
                            (run_id, scope.user_id, scope.workspace_id)).fetchone()[0])
            if run["status"] in TERMINAL:
                return run
            message_row = db.execute("SELECT body FROM records WHERE id=?", (run["assistant_message_id"],)).fetchone()
            message = json.loads(message_row["body"])
            message.update(text=text, blocks=blocks, status="completed")
            Database.update(db, message)
            run.update(status="completed", message_id=message["id"])
            Database.update(db, run)
            self.emit(db, run_id, "state", {"status": "completed"})
            self.emit(db, run_id, "final", {"message": message})
            return run
        return await self.db.call(write)

    async def recover(self):
        """Never replay interrupted external actions: fail them visibly after restart."""
        def write(db):
            for row in db.execute("SELECT body FROM records WHERE kind IN ('run','job','tool_run')").fetchall():
                item = json.loads(row[0])
                if item.get("status") not in TERMINAL | {"success", "error", "indexed"}:
                    item.update(status="failed", error="Server restarted; submit a new request to retry.")
                    Database.update(db, item)
                    if "request" in item:
                        self.emit(db, item["id"], "state", {"status": "failed", "error": item["error"]})
        await self.db.call(write)
