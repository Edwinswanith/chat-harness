import asyncio


class JobService:
    def __init__(self, repo, queue):
        self.repo, self.queue = repo, queue

    async def submit(self, scope, thread_id, kind, **body):
        job = await self.repo.create("job", scope, thread_id, kind=kind, status="queued", **body)
        await self.queue.put(job["id"], scope)
        return job

    async def wait(self, job_id, scope, timeout=45):
        async def poll():
            while True:
                job = await self.repo.get("job", job_id, scope)
                if job["status"] in {"completed", "failed", "cancelled"}:
                    return job
                await asyncio.sleep(0.05)
        return await asyncio.wait_for(poll(), timeout)

    async def list(self, scope, thread_id):
        await self.repo.get("thread", thread_id, scope)
        return await self.repo.list("job", scope, thread_id)
