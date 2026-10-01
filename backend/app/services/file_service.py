from pathlib import Path
import asyncio
import hashlib
import mimetypes
from uuid import uuid4

from app.storage.paths import file_key


ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf"}


class FileService:
    def __init__(self, repo, storage, jobs, max_bytes):
        self.repo, self.storage, self.jobs, self.max_bytes = repo, storage, jobs, max_bytes

    async def upload(self, scope, thread_id, name, content):
        await self.repo.get("thread", thread_id, scope)
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError("Only .txt, .md, .csv, and .pdf files are supported")
        if not content or len(content) > self.max_bytes:
            raise ValueError("Source file must be nonempty and within the upload limit")
        if suffix == ".pdf":
            if not content.startswith(b"%PDF-"):
                raise ValueError("Invalid PDF file")
        else:
            try:
                content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("Source files must use UTF-8") from exc
        source_id = uuid4().hex
        key = file_key(source_id, scope=scope, thread_id=thread_id, name=name)
        derived_key = file_key(source_id, derived=True, scope=scope, thread_id=thread_id, name=name)
        await self.storage.write(key, content)
        source = await self.repo.create("file", scope, thread_id, id=source_id, name=name,
            filename=name, original_filename=name, key=key, derived_key=derived_key, size=len(content),
            size_bytes=len(content), mime_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
            source_sha256=hashlib.sha256(content).hexdigest(), storage=self.storage.metadata(key), status="queued")
        await self.jobs.submit(scope, thread_id, "ingestion", source_id=source_id)
        return source

    async def get_source(self, source_id, scope, thread_id=None):
        source = await self.repo.get("file", source_id, scope)
        if thread_id is not None and source["thread_id"] != thread_id:
            raise KeyError("Source is not attached to this thread")
        return source

    async def wait_for_index(self, source_id, scope, thread_id, timeout=45):
        for _ in range(timeout * 10):
            source = await self.get_source(source_id, scope, thread_id)
            if source["status"] == "indexed":
                return source
            if source["status"] == "failed":
                raise ValueError(source.get("error", "Source ingestion failed"))
            await asyncio.sleep(.1)
        raise ValueError("Source indexing timed out")

    async def list(self, scope, thread_id):
        await self.repo.get("thread", thread_id, scope)
        return await self.repo.list("file", scope, thread_id)

    async def index_artifact(self, scope, artifact):
        data = await self.storage.read(artifact["key"])
        return await self.upload(scope, artifact["thread_id"], artifact["name"], data)
