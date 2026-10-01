import asyncio
import json
from app.schemas.contracts import ToolResult


class JobWorker:
    def __init__(self, queue, repo, sandbox, artifacts, ingestion, publisher=None):
        self.queue, self.repo, self.sandbox = queue, repo, sandbox
        self.artifacts, self.ingestion = artifacts, ingestion
        self.task = None
        self.publisher = publisher

    def start(self):
        self.task = asyncio.create_task(self.work())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def work(self):
        while True:
            job_id, scope = await self.queue.get()
            job = {}
            try:
                job = await self.repo.get("job", job_id, scope)
                await self.repo.patch("job", job_id, scope, status="running")
                if job["kind"] == "ingestion":
                    await self.ingestion.ingest(scope, job["source_id"])
                    await self.repo.patch("job", job_id, scope, status="completed")
                else:
                    if self.publisher:
                        async with self.publisher.action(job['run']['id'], 'worker', 'JobWorker', 'Processing queued artifact', {'job_id': job_id}) as event:
                            await self.execute_artifact(job, scope)
                    else:
                        await self.execute_artifact(job, scope)
            except asyncio.CancelledError:
                await self.repo.patch("job", job_id, scope, status="cancelled")
                raise
            except Exception as exc:
                await self.repo.patch("job", job_id, scope, status="failed", error=str(exc)[:500])
                if job.get("kind") == "ingestion":
                    await self.repo.patch("file", job["source_id"], scope, status="failed", error=str(exc)[:500])
            finally:
                self.queue.done()

    async def execute_artifact(self, job, scope):
        code = ("from pathlib import Path\n"
                f"Path('/output/{job['name']}').write_text({json.dumps(job['content'])}, encoding='utf-8')\n")
        if self.publisher:
            async with self.publisher.action(job['run']['id'], 'sandbox', 'Sandbox', 'Executing artifact job', {'job_id': job['id'], 'target': job['name']}) as event:
                response = await self.sandbox.execute(code, {})
                event.update(exit_code=response.get('exit_code'), passed=response.get('exit_code') == 0, output_count=len(response.get('outputs', [])))
        else:
            response = await self.sandbox.execute(code, {})
        if response.get("exit_code") != 0:
            raise ValueError("Sandbox execution failed: " + response.get("stderr", "")[:300])
        outputs = response.get("outputs", [])
        if len(outputs) != 1 or outputs[0].get("name") != job["name"]:
            raise ValueError("Sandbox did not produce the expected output")
        # Validate before storing any artifact metadata.
        artifact = await self.artifacts.publish(scope, job["run"], outputs[0], job["source_ids"])
        if self.publisher:
            await self.publisher.emit(run_id=job['run']['id'], event_type='artifact.completed', component='artifact', component_name='ArtifactService', summary='Published validated artifact ' + job['name'], details={'artifact_id': artifact['id'], 'job_id': job['id']})
        result = ToolResult(status="success", artifact_ids=[artifact["id"]], data={"job_id": job["id"]})
        await self.repo.patch("job", job["id"], scope, status="completed", result=result.model_dump())
