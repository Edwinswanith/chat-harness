from pathlib import Path
import hashlib
import mimetypes
from uuid import uuid4
from app.storage.paths import artifact_key
from app.validation.artifact_validator import validate_output


MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class ArtifactService:
    def __init__(self, repo, storage):
        self.repo, self.storage = repo, storage

    async def publish(self, scope, run, output, source_ids):
        name, data = validate_output(output)
        artifact_id = uuid4().hex
        key = artifact_key(artifact_id, name, scope, run["thread_id"])
        await self.storage.write(key, data)
        return await self.repo.create("artifact", scope, run["thread_id"], id=artifact_id,
            name=name, key=key, size=len(data), run_id=run["id"], source_ids=source_ids,
            size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), storage=self.storage.metadata(key),
            media_type=MEDIA_TYPES.get(Path(name).suffix.lower(), mimetypes.guess_type(name)[0] or "text/plain"))

    async def download(self, artifact_id, scope):
        artifact = await self.repo.get("artifact", artifact_id, scope)
        return artifact, await self.storage.read(artifact["key"])
