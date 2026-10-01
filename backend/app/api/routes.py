from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.core.security import scoped_auth
from app.schemas.contracts import MessageRequest, SearchRequest, Scope


def build_router(container):
    router = APIRouter(prefix="/api")
    scope = scoped_auth(container.authenticator)

    def error(exc):
        if isinstance(exc, KeyError):
            raise HTTPException(status_code=404, detail="Resource not found") from exc
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise exc

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    @router.post("/chats")
    async def create_chat(auth: Scope = Depends(scope)):
        return await container.chat.create_thread(auth)

    @router.get("/conversations")
    async def conversations(mode: str | None = None, project_workspace_id: str | None = None, auth: Scope = Depends(scope)):
        return await container.chat.conversations(auth, mode, project_workspace_id)

    @router.post("/conversations")
    async def create_conversation(auth: Scope = Depends(scope)):
        return await container.chat.create_thread(auth)

    @router.get("/workspaces/available")
    async def available_workspaces(auth: Scope = Depends(scope)):
        return container.workspaces.available()

    @router.get("/workspaces")
    async def workspaces(auth: Scope = Depends(scope)):
        return await container.workspaces.list(auth)

    @router.post("/workspaces")
    async def create_workspace(body: dict, auth: Scope = Depends(scope)):
        try:
            return await container.workspaces.create(auth, body.get("path", ""), body.get("name"))
        except Exception as exc:
            error(exc)

    @router.delete("/workspaces/{workspace_id}")
    async def delete_workspace(workspace_id: str, auth: Scope = Depends(scope)):
        try:
            return await container.workspaces.remove(auth, workspace_id)
        except Exception as exc:
            error(exc)

    @router.get("/workspaces/{workspace_id}/tree")
    async def workspace_tree(workspace_id: str, path: str = ".", auth: Scope = Depends(scope)):
        try:
            return await container.workspaces.tree(auth, workspace_id, path)
        except Exception as exc:
            error(exc)

    @router.get("/workspaces/{workspace_id}/conversations")
    async def workspace_conversations(workspace_id: str, auth: Scope = Depends(scope)):
        try:
            await container.workspaces.get(auth, workspace_id)
            return await container.chat.conversations(auth, mode="workspace", project_workspace_id=workspace_id)
        except Exception as exc:
            error(exc)

    @router.get("/workspaces/{workspace_id}/files")
    async def workspace_file(workspace_id: str, path: str, auth: Scope = Depends(scope)):
        try:
            return await container.workspaces.read(auth, workspace_id, path)
        except Exception as exc:
            error(exc)

    @router.get("/workspaces/{workspace_id}/image")
    async def workspace_image(workspace_id: str, path: str, auth: Scope = Depends(scope)):
        from fastapi.responses import FileResponse
        try:
            workspace = await container.workspaces.get(auth, workspace_id)
            resolved = container.workspaces.provider.resolve(workspace['root_id'], path)
            formats = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.webp':'image/webp', '.gif':'image/gif'}
            if resolved.suffix.lower() not in formats or not resolved.is_file(): raise KeyError('Image unavailable')
            return FileResponse(resolved, media_type=formats[resolved.suffix.lower()], headers={'Cache-Control':'no-store'})
        except Exception as exc:
            error(exc)

    @router.get("/workspaces/{workspace_id}/changes")
    async def workspace_changes_for_run(workspace_id: str, run_id: str, auth: Scope = Depends(scope)):
        try:
            run = await container.run_service.get(run_id, auth)
            if run.get("project_workspace_id") != workspace_id:
                raise KeyError("Run is outside this workspace")
            return await container.workspaces.changes(auth, workspace_id, run_id)
        except Exception as exc:
            error(exc)

    @router.get("/workspaces/{workspace_id}/runs/{run_id}/preview/{viewport}")
    async def workspace_screenshot(workspace_id: str, run_id: str, viewport: str, auth: Scope = Depends(scope)):
        from pathlib import Path
        from fastapi.responses import FileResponse
        try:
            run = await container.run_service.get(run_id, auth)
            if run.get('project_workspace_id') != workspace_id or viewport not in {'desktop', 'mobile'}:
                raise KeyError('Preview unavailable')
            workspace = await container.workspaces.get(auth, workspace_id)
            root = container.workspaces.provider.root(workspace['root_id'])
            path = (root / '.harness-preview' / f'{run_id}-{viewport}.png').resolve()
            if not path.is_relative_to(root) or not path.is_file(): raise KeyError('Preview unavailable')
            return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'no-store'})
        except Exception as exc:
            error(exc)

    @router.post("/workspaces/{workspace_id}/conversations")
    async def create_workspace_conversation(workspace_id: str, auth: Scope = Depends(scope)):
        try:
            await container.workspaces.get(auth, workspace_id)
            return await container.chat.create_thread(auth, mode="workspace", project_workspace_id=workspace_id)
        except Exception as exc:
            error(exc)

    @router.get("/conversations/{conversation_id}")
    async def conversation(conversation_id: str, auth: Scope = Depends(scope)):
        try:
            return await container.chat.conversation(auth, conversation_id)
        except Exception as exc:
            error(exc)

    @router.patch("/conversations/{conversation_id}")
    async def update_conversation(conversation_id: str, body: dict, auth: Scope = Depends(scope)):
        try:
            return await container.chat.update_conversation(auth, conversation_id, body.get("title"), body.get("status"))
        except Exception as exc:
            error(exc)

    @router.delete("/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str, auth: Scope = Depends(scope)):
        try:
            return await container.chat.update_conversation(auth, conversation_id, status="deleted")
        except Exception as exc:
            error(exc)

    @router.get("/conversations/{conversation_id}/messages")
    async def conversation_messages(conversation_id: str, cursor: str | None = None, limit: int = 100,
                                    auth: Scope = Depends(scope)):
        try:
            return await container.chat.paged_messages(auth, conversation_id, cursor, min(max(limit, 1), 200))
        except Exception as exc:
            error(exc)

    @router.get("/conversations/{conversation_id}/runs")
    async def conversation_runs(conversation_id: str, auth: Scope = Depends(scope)):
        try:
            await container.chat.conversation(auth, conversation_id)
            return await container.repo.list("run", auth, conversation_id)
        except Exception as exc:
            error(exc)

    @router.get("/conversations/{conversation_id}/active-run")
    async def active_run(conversation_id: str, auth: Scope = Depends(scope)):
        try:
            return await container.chat.active_run(auth, conversation_id)
        except Exception as exc:
            error(exc)

    @router.get("/chats/{thread_id}/messages")
    async def messages(thread_id: str, auth: Scope = Depends(scope)):
        try:
            return await container.chat.messages(auth, thread_id)
        except Exception as exc:
            error(exc)

    @router.post("/messages")
    async def submit(request: MessageRequest, auth: Scope = Depends(scope)):
        try:
            return await container.chat.submit(auth, request)
        except Exception as exc:
            error(exc)

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str, auth: Scope = Depends(scope)):
        try:
            return await container.run_service.get(run_id, auth)
        except Exception as exc:
            error(exc)

    @router.post("/runs/{run_id}/cancel")
    async def cancel(run_id: str, auth: Scope = Depends(scope)):
        try:
            return await container.chat.cancel(auth, run_id)
        except Exception as exc:
            error(exc)

    @router.get("/runs/{run_id}/events")
    async def events(run_id: str, after: int = 0, auth: Scope = Depends(scope)):
        return StreamingResponse(container.run_service.stream(run_id, auth, after), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @router.get("/runs/{run_id}/activity")
    async def activity(run_id: str, after: int = 0, auth: Scope = Depends(scope)):
        try:
            return await container.run_service.activity(run_id, auth, after)
        except Exception as exc:
            error(exc)

    @router.get("/runs/{run_id}/changes")
    async def workspace_changes(run_id: str, auth: Scope = Depends(scope)):
        try:
            run = await container.run_service.get(run_id, auth)
            workspace_id = run.get("project_workspace_id")
            if not workspace_id:
                raise ValueError("This run is not a workspace run")
            return await container.workspaces.changes(auth, workspace_id, run_id)
        except Exception as exc:
            error(exc)

    @router.post("/runs/{run_id}/revert")
    async def revert_workspace_run(run_id: str, auth: Scope = Depends(scope)):
        try:
            run = await container.run_service.get(run_id, auth)
            workspace_id = run.get("project_workspace_id")
            if not workspace_id:
                raise ValueError("This run is not a workspace run")
            return await container.workspaces.revert(auth, workspace_id, run_id)
        except Exception as exc:
            error(exc)

    @router.post("/files")
    async def upload(thread_id: str = Form(...), file: UploadFile = File(...), auth: Scope = Depends(scope)):
        try:
            return await container.files.upload(auth, thread_id, file.filename or "upload.txt", await file.read())
        except Exception as exc:
            error(exc)

    @router.get("/files")
    async def files(thread_id: str, auth: Scope = Depends(scope)):
        try:
            return await container.files.list(auth, thread_id)
        except Exception as exc:
            error(exc)

    @router.get("/jobs")
    async def jobs(thread_id: str, auth: Scope = Depends(scope)):
        try:
            return await container.jobs.list(auth, thread_id)
        except Exception as exc:
            error(exc)

    @router.get("/artifacts/{artifact_id}/download")
    async def download(artifact_id: str, auth: Scope = Depends(scope)):
        try:
            artifact, data = await container.artifacts.download(artifact_id, auth)
            return Response(data, media_type="application/octet-stream",
                            headers={"Content-Disposition": f'attachment; filename="{artifact["name"]}"'})
        except Exception as exc:
            error(exc)

    @router.post("/artifacts/{artifact_id}/index")
    async def index_artifact(artifact_id: str, auth: Scope = Depends(scope)):
        try:
            artifact = await container.repo.get("artifact", artifact_id, auth)
            return await container.files.index_artifact(auth, artifact)
        except Exception as exc:
            error(exc)

    @router.post("/rag/search")
    async def search(request: SearchRequest, auth: Scope = Depends(scope)):
        try:
            return await container.rag.retrieve(auth, request.thread_id, request.query, request.file_ids)
        except Exception as exc:
            error(exc)

    return router
