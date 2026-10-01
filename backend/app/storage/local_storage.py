import asyncio
from pathlib import Path


class LocalStorage:
    def __init__(self, root):
        self.provider = "local"
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Invalid storage key")
        return path

    async def write(self, key, data):
        def write():
            path = self.path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        await asyncio.to_thread(write)

    async def read(self, key):
        return await asyncio.to_thread(self.path(key).read_bytes)

    def metadata(self, key):
        return {"provider": self.provider, "key": key}
