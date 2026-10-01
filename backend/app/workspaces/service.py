import asyncio
import time
import re
import difflib
from app.harness.execution_events import sanitize
from app.workspaces.provider import WorkspaceReadError, WorkspaceEditError


class WorkspaceService:
    def __init__(self, repo, provider):
        self.repo, self.provider = repo, provider

    def available(self):
        return self.provider.available()

    async def create(self, scope, root_path, name=None):
        root_id, root = self.provider.register(root_path)
        for workspace in await self.list(scope):
            if workspace.get("root_path") == str(root):
                self.provider.roots.pop(root_id, None)
                await self.repo.patch("workspace", workspace["id"], scope, updated_at=time.time())
                return workspace
        workspace = await self.repo.create("workspace", scope, "", name=name or root.name, root_id=root_id,
            root_path=str(root), provider="local", mode="filesystem_workspace", status="active", settings={"allow_terminal": True,
            "allow_file_creation": True, "allow_file_deletion": True, "allow_git": True, "auto_index": True})
        await self.repo.create("workspace_session", scope, "", project_workspace_id=workspace["id"], status="active",
                               started_at=time.time(), last_activity_at=time.time())
        return workspace

    async def list(self, scope):
        return [item for item in await self.repo.list("workspace", scope) if item.get("status") == "active"]

    async def remove(self, scope, workspace_id):
        workspace = await self.get(scope, workspace_id)
        await self.repo.patch("workspace", workspace_id, scope, status="archived", updated_at=time.time())
        for conversation in await self.repo.list("thread", scope):
            if conversation.get("mode") == "workspace" and conversation.get("project_workspace_id") == workspace_id:
                await self.repo.patch("thread", conversation["id"], scope, status="archived", updated_at=time.time())
        return {"id": workspace["id"], "status": "archived"}

    async def get(self, scope, workspace_id):
        workspace = await self.repo.get("workspace", workspace_id, scope)
        if workspace["root_id"] not in self.provider.roots:
            self.provider.restore(workspace["root_id"], workspace["root_path"])
        return workspace

    async def tree(self, scope, workspace_id, path="."):
        workspace = await self.get(scope, workspace_id)
        entries = await self.provider.list_files(workspace["root_id"], path)
        return {"workspace_id": workspace_id, "path": path, "entries": entries}

    async def inspect(self, scope, workspace_id):
        """Refresh metadata from disk and return a compact, model-safe project summary."""
        workspace = await self.get(scope, workspace_id)
        files = await self.provider.scan_files(workspace["root_id"])
        known = {item.get("relative_path"): item for item in await self.repo.list("workspace_file", scope)
                 if item.get("project_workspace_id") == workspace_id}
        now = time.time()
        for metadata in files:
            existing = known.pop(metadata["relative_path"], None)
            payload = dict(project_workspace_id=workspace_id, indexed=True, updated_at=now, **metadata)
            if existing:
                await self.repo.patch("workspace_file", existing["id"], scope, **payload)
            else:
                await self.repo.create("workspace_file", scope, "", **payload)
        for stale in known.values():
            await self.repo.patch("workspace_file", stale["id"], scope, indexed=False, missing=True, updated_at=now)
        paths = {item["relative_path"] for item in files}
        def has(*names): return next((name for name in names if name in paths), None)
        package = has("package.json"); pyproject = has("pyproject.toml"); readme = has("README.md", "README")
        framework = "Vite" if has("vite.config.ts", "vite.config.js") else "React" if any(path.startswith("src/") and path.endswith((".tsx", ".jsx")) for path in paths) else "unknown"
        result = {"workspace_id": workspace_id, "name": workspace["name"], "project_type": "frontend" if package else "python" if pyproject else "unknown",
                  "framework": framework, "package_manager": "npm" if package else None,
                  "build_command": "npm run build" if package else None, "important_files": [item for item in (package, pyproject, readme, has("src/App.tsx", "src/App.jsx")) if item],
                  "file_count": len(files), "files": [item["relative_path"] for item in files[:100]]}
        await self.repo.patch("workspace", workspace_id, scope, inspection=result, last_inspected_at=now, updated_at=now)
        return result

    async def read(self, scope, workspace_id, path, offset_bytes=0, max_bytes=200_000):
        return await self.provider.read_file((await self.get(scope, workspace_id))["root_id"], path, limit=max_bytes, offset_bytes=offset_bytes)

    async def _read_for_edit(self, scope, workspace_id, path):
        current = await self.read(scope, workspace_id, path)
        if current['size_bytes'] > 500_000:
            raise ValueError("Workspace file exceeds the write limit")
        contents = [current['content']]
        page = current
        while page['truncated']:
            page = await self.read(scope, workspace_id, path, offset_bytes=page['next_offset_bytes'])
            if page['sha256'] != current['sha256']:
                raise WorkspaceEditError('file_changed', path, "File changed while reading. Read it again before editing.")
            contents.append(page['content'])
        return {**current, 'content': ''.join(contents), 'truncated': False}

    async def context(self, scope, workspace_id):
        inspection = await self.inspect(scope, workspace_id)
        return {"workspace": inspection["name"], "files": inspection["files"], "important_files": inspection["important_files"],
                "project_type": inspection["project_type"], "framework": inspection["framework"]}

    async def retrieve(self, scope, workspace_id, query, limit=6):
        """Bounded lexical workspace retrieval; return source text only to model context."""
        inspection = (await self.get(scope, workspace_id)).get('inspection') or await self.inspect(scope, workspace_id)
        terms = {term for term in re.findall(r'[a-zA-Z]{3,}', query.lower()) if term not in {'the', 'build', 'create', 'this', 'with', 'use'}}
        chunks = []
        for path in inspection.get('files', []):
            if not path.endswith(('.md', '.json', '.jsx', '.tsx', '.js', '.ts', '.css', '.html')): continue
            try: source = await self.read(scope, workspace_id, path)
            except (KeyError, ValueError): continue
            text = source['content'][:12000]
            score = sum(text.lower().count(term) for term in terms) + sum(term in path.lower() for term in terms)
            if score or path in inspection.get('important_files', []):
                chunks.append({'path': path, 'score': score, 'text': text[:3000]})
        chunks.sort(key=lambda item: item['score'], reverse=True)
        return {'query': query, 'scope': 'selected workspace', 'files_searched': len(inspection.get('files', [])), 'chunks': chunks[:limit]}

    async def write(self, scope, workspace_id, path, content, expected_sha256=None, create=False, run_id=None, operation=None):
        workspace = await self.get(scope, workspace_id)
        if not workspace["settings"].get("allow_file_creation", False):
            raise ValueError("Workspace file creation is disabled")
        try:
            before = (await self._read_for_edit(scope, workspace_id, path))["content"]
        except WorkspaceReadError as exc:
            if exc.code != 'file_not_found': raise
            before = ""
        change = await self.provider.write_file(workspace["root_id"], path, content, expected_sha256, create)
        change['diff'] = sanitize(''.join(difflib.unified_diff(before.splitlines(keepends=True), content.splitlines(keepends=True), fromfile=path, tofile=path))[:20000])
        await self.repo.create("workspace_change", scope, "", project_workspace_id=workspace_id, run_id=run_id,
                               operation=operation or ("create" if create else "write"), **change)
        return change

    async def patch(self, scope, workspace_id, path, find, replace, expected_sha256=None, run_id=None):
        current = await self._read_for_edit(scope, workspace_id, path)
        if expected_sha256 and expected_sha256 != current['sha256']:
            raise WorkspaceEditError('file_changed', path,
                "File changed since it was read. Read the latest file, recompute the edit, and retry with its current sha256. Never reuse an old hash or remove hash protection.", current['sha256'])
        if find not in current["content"]:
            raise WorkspaceEditError('patch_not_found', path,
                "Patch text was not found in the current file. Read the latest file and choose an exact matching replacement.", current['sha256'])
        change = await self.write(scope, workspace_id, path, current["content"].replace(find, replace, 1), expected_sha256 or current["sha256"], run_id=run_id, operation="patch")
        return change

    async def build(self, scope, workspace_id):
        return await self._run_task(scope, workspace_id, "npm run build")

    async def test(self, scope, workspace_id):
        return await self._run_task(scope, workspace_id, "npm test")

    async def lint(self, scope, workspace_id):
        return await self._run_task(scope, workspace_id, "npm run lint")

    async def _run_task(self, scope, workspace_id, command):
        started = time.monotonic()
        result = await self.command(scope, workspace_id, command, timeout=60)
        return {"command": command, "exit_code": result["exit_code"], "stdout": result["stdout"],
                "stderr_tail": result["stderr"], "duration_ms": int((time.monotonic() - started) * 1000),
                "status": "success" if result["exit_code"] == 0 else "failed", "retryable": result["exit_code"] != 0,
                "passed": result["exit_code"] == 0}

    async def search(self, scope, workspace_id, query, path="."):
        return await self.provider.search_text((await self.get(scope, workspace_id))["root_id"], query, path)

    async def create_directory(self, scope, workspace_id, path, run_id=None):
        workspace = await self.get(scope, workspace_id)
        change = await self.provider.create_directory(workspace["root_id"], path)
        await self.repo.create("workspace_change", scope, "", project_workspace_id=workspace_id, run_id=run_id, operation="mkdir", **change)
        return change

    async def rename(self, scope, workspace_id, path, target_path, run_id=None):
        workspace = await self.get(scope, workspace_id)
        change = await self.provider.rename_path(workspace["root_id"], path, target_path)
        await self.repo.create("workspace_change", scope, "", project_workspace_id=workspace_id, run_id=run_id, operation="rename", **change)
        return change

    async def delete(self, scope, workspace_id, path, run_id=None):
        workspace = await self.get(scope, workspace_id)
        if not workspace["settings"].get("allow_file_deletion", False):
            raise ValueError("Workspace deletion is disabled")
        change = await self.provider.delete_path(workspace["root_id"], path)
        await self.repo.create("workspace_change", scope, "", project_workspace_id=workspace_id, run_id=run_id, operation="delete", **change)
        return change

    async def command(self, scope, workspace_id, command, cwd=".", timeout=60):
        workspace = await self.get(scope, workspace_id)
        if not workspace["settings"].get("allow_terminal", False):
            raise ValueError("Terminal execution is disabled for this workspace")
        return await self.provider.run_command(workspace["root_id"], command, cwd, timeout)

    async def changes(self, scope, workspace_id, run_id):
        await self.get(scope, workspace_id)
        return [change for change in await self.repo.list("workspace_change", scope)
                if change.get("project_workspace_id") == workspace_id and change.get("run_id") == run_id]

    async def revert(self, scope, workspace_id, run_id):
        workspace = await self.get(scope, workspace_id)
        changes = list(reversed(await self.changes(scope, workspace_id, run_id)))
        restored, skipped = [], []
        for change in changes:
            try:
                operation, path = change.get("operation"), change.get("path")
                if operation == "create":
                    current = await self.provider.read_file(workspace["root_id"], path)
                    if current["sha256"] != change.get("after_sha256"):
                        raise ValueError("File changed after this run")
                    await self.provider.delete_path(workspace["root_id"], path)
                elif operation in {"write", "patch"}:
                    await self.provider.restore_snapshot(workspace["root_id"], path, change.get("before_snapshot"), change.get("after_sha256"))
                elif operation == "rename":
                    await self.provider.rename_path(workspace["root_id"], change["target_path"], path)
                else:
                    skipped.append({"path": path, "reason": "This operation requires manual recovery"})
                    continue
                restored.append(path)
            except (ValueError, KeyError) as exc:
                skipped.append({"path": change.get("path"), "reason": str(exc)})
        await self.repo.create("workspace_change", scope, "", project_workspace_id=workspace_id, run_id=run_id,
                               operation="revert", restored=restored, skipped=skipped)
        return {"restored": restored, "skipped": skipped}
