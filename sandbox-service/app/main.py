import base64
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.execution.docker_runner import DockerRunner


class ExecutionRequest(BaseModel):
    code: str = Field(min_length=1, max_length=600_000)
    inputs: dict = Field(default_factory=dict)


def create_app(runner=None):
    app = FastAPI(title="AI Harness Sandbox")
    active_runner = runner or DockerRunner(os.getenv("SANDBOX_RUNNER_IMAGE", "simple-ai-harness-runner"))
    token = os.getenv("SANDBOX_TOKEN", "local-sandbox-token")

    def authorize(value):
        if value != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="Invalid sandbox token")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/executions")
    async def execute(request: ExecutionRequest, authorization: str | None = Header(default=None)):
        authorize(authorization)
        result = await active_runner.execute(request.code, request.inputs)
        return result

    return app


app = create_app()
