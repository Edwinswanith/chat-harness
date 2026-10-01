import asyncio

import httpx

from app.core.config import Settings
from app.core.container import AppContainer
from app.main import create_app


def test_bearer_scope_and_upload_isolation(tmp_path):
    asyncio.run(scenario(tmp_path))


async def scenario(tmp_path):
    settings = Settings(data_dir=tmp_path, tokens={"alice": ["alice", "workspace"], "bob": ["bob", "workspace"]})
    app = create_app(AppContainer(settings))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        preflight = await client.options("/api/conversations", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET"})
        assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
        assert (await client.post("/api/chats")).status_code == 401
        headers = {"Authorization": "Bearer alice"}
        thread = (await client.post("/api/chats", headers=headers)).json()
        workspace_path = tmp_path / "workspace"; workspace_path.mkdir()
        workspace = (await client.post("/api/workspaces", headers=headers, json={"path": str(workspace_path)})).json()
        workspace_chat = (await client.post(f"/api/workspaces/{workspace['id']}/conversations", headers=headers)).json()
        workspace_chats = (await client.get(f"/api/workspaces/{workspace['id']}/conversations", headers=headers)).json()
        assert [item["id"] for item in workspace_chats] == [workspace_chat["id"]]
        assert (await client.get(f"/api/conversations/{workspace_chat['id']}", headers=headers)).json()["mode"] == "workspace"
        assert (await client.get(f"/api/conversations/{workspace_chat['id']}", headers=headers)).json()["project_workspace_id"] == workspace["id"]
        assert (await client.delete(f"/api/workspaces/{workspace['id']}", headers=headers)).json()["status"] == "archived"
        assert (await client.get("/api/workspaces", headers=headers)).json() == []
        response = await client.post("/api/files", headers=headers, data={"thread_id": thread["id"]},
                                     files={"file": ("notes.md", b"# Notes\nSafe source", "text/markdown")})
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        blocked = await client.get(f"/api/files?thread_id={thread['id']}", headers={"Authorization": "Bearer bob"})
        assert blocked.status_code == 404
