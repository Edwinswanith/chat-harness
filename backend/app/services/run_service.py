import asyncio
import json
from app.repositories.run_repository import TERMINAL


class RunService:
    def __init__(self, runs, repo):
        self.repository, self.repo = runs, repo
        from app.harness.execution_events import ExecutionEventPublisher
        self.publisher = ExecutionEventPublisher(runs)

    async def get(self, run_id, scope):
        return await self.repo.get("run", run_id, scope)

    async def claim(self, run_id, scope):
        return await self.repository.claim(run_id, scope)

    async def transition(self, run_id, scope, status, **changes):
        return await self.repository.transition(run_id, scope, status, **changes)

    async def event(self, run_id, name, data):
        await self.publisher.emit(run_id=run_id, event_type=name, component=data.get("component", name.split(".")[0]),
                                  summary=data.get("summary", name.replace(".", " ").capitalize()), details=data)

    async def append_delta(self, run_id, scope, text):
        await self.repository.append_delta(run_id, scope, text)

    async def activity(self, run_id, scope, after=0):
        await self.get(run_id, scope)
        return await self.repository.events(run_id, after)

    async def stream(self, run_id, scope, after=0):
        await self.get(run_id, scope)
        while True:
            events = await self.repository.events(run_id, after)
            for event in events:
                after = event["seq"]
                yield f"id: {after}\nevent: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            if (await self.get(run_id, scope))["status"] in TERMINAL:
                break
            if not events:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.15)
