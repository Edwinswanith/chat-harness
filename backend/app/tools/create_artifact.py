from pydantic import BaseModel, ConfigDict, Field
from app.schemas.contracts import ToolResult


class ArtifactArguments(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+\.(md|txt|csv)$")
    content: str = Field(min_length=1, max_length=500000)
    source_ids: list[str] = Field(default_factory=list, max_length=10)

    model_config = ConfigDict(extra="forbid")


class CreateArtifact:
    name = "create_artifact"
    description = "Create a UTF-8 report from approved sources in an isolated sandbox."
    schema = ArtifactArguments
    modes = {"chatbot"}

    def __init__(self, jobs, files):
        self.jobs, self.files = jobs, files

    async def execute(self, scope, run, arguments):
        approved = run["request"].get("file_ids", [])
        for source_id in arguments.source_ids:
            if source_id not in approved:
                raise ValueError("Source was not approved for this request")
            await self.files.get_source(source_id, scope, run["thread_id"])
        job = await self.jobs.submit(scope, run["thread_id"], "sandbox", run=run, **arguments.model_dump())
        job = await self.jobs.wait(job["id"], scope)
        if job["status"] != "completed":
            return ToolResult(status="error", error=job.get("error", "Job cancelled"), retryable=False)
        return ToolResult.model_validate(job["result"])
