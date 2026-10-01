import asyncio
import json
import sqlite3
import time
from uuid import uuid4


class Database:
    """Short transactions; SQLite is the durable source of entity and job truth."""

    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL, thread_id TEXT NOT NULL,
                    body TEXT NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS records_scope
                    ON records(kind,user_id,workspace_id,thread_id,created);
                CREATE TABLE IF NOT EXISTS request_keys (
                    user_id TEXT, workspace_id TEXT, key TEXT, run_id TEXT,
                    PRIMARY KEY(user_id,workspace_id,key));
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, body TEXT);
                CREATE TABLE IF NOT EXISTS vectors (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    source_id TEXT NOT NULL, thread_id TEXT NOT NULL, text TEXT NOT NULL,
                    embedding TEXT NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS vectors_scope
                    ON vectors(user_id,workspace_id,source_id,created);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    async def call(self, fn):
        return await asyncio.to_thread(self._call, fn)

    def _call(self, fn):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return fn(db)

    @staticmethod
    def insert(db, kind, scope, thread_id, body):
        item = dict(body, id=body.get("id", uuid4().hex), user_id=scope.user_id,
                    workspace_id=scope.workspace_id, thread_id=thread_id,
                    conversation_id=body.get("conversation_id", thread_id))
        db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?)", (
            kind, item["id"], scope.user_id, scope.workspace_id, thread_id,
            json.dumps(item), time.time()))
        return item

    @staticmethod
    def update(db, item):
        db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(item), item["id"]))
