import asyncio


class JobQueue:
    """Dispatch only; job records remain durable in the repository."""

    def __init__(self):
        self.queue = asyncio.Queue(maxsize=100)

    async def put(self, job_id, scope):
        await self.queue.put((job_id, scope))

    async def get(self):
        return await self.queue.get()

    def done(self):
        self.queue.task_done()
