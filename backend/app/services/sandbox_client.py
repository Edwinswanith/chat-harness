from typing import Protocol
import httpx


class SandboxClient(Protocol):
    async def execute(self, code: str, inputs: dict) -> dict: ...


class HttpSandboxClient:
    def __init__(self, url, token):
        self.url, self.token = url, token

    async def execute(self, code, inputs):
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(self.url + "/executions", json={"code": code, "inputs": inputs},
                                         headers={"Authorization": "Bearer " + self.token})
            response.raise_for_status()
            return response.json()
