import asyncio
import codecs
import fnmatch
import hashlib
import os
import signal
import subprocess
import shutil
from pathlib import Path
from uuid import uuid4


IGNORED = {".git", "node_modules", "dist", "build", "coverage", ".next", ".cache", "__pycache__", ".venv", "venv", "tmp", ".harness-trash", ".harness-preview"}
SENSITIVE = {".env", "id_rsa", "credentials.json"}
BLOCKED_COMMANDS = {"sudo", "rm", "shutdown", "reboot", "mkfs", "dd", "curl", "wget", "chmod"}
ALLOWED_COMMANDS = (("npm", "create"), ("npm", "init"), ("npm", "install"), ("npm", "run"), ("npm", "test"),
                    ("npx", "create-vite"), ("npx", "vite"), ("pnpm",), ("yarn",),
                    ("pytest",), ("python", "-m", "pytest"), ("pip", "install", "-r"), ("git", "status"),
                    ("git", "diff"), ("git", "log"))


class WorkspaceCommandPolicyError(ValueError):
    """A rejected command was never executed; choose an approved alternative."""


class WorkspaceFileExistsError(ValueError):
    """Recoverable create conflict; never authorizes an implicit overwrite."""


class WorkspaceReadError(ValueError):
    def __init__(self, code, path, message, recovery):
        super().__init__(message)
        self.code, self.path, self.recovery = code, path, recovery


class WorkspaceEditError(ValueError):
    def __init__(self, code, path, message, current_sha256=None):
        super().__init__(message)
        self.code, self.path, self.current_sha256 = code, path, current_sha256
        self.recovery = 'read_then_recompute_edit'


class LocalWorkspaceProvider:
    def __init__(self, roots=None):
        self.roots = {key: Path(value).resolve() for key, value in (roots or {}).items()}

    def available(self):
        return [{"id": key, "name": path.name} for key, path in self.roots.items() if path.is_dir()]

    def root(self, root_id):
        root = self.roots.get(root_id)
        if not root or not root.is_dir():
            raise KeyError("Workspace root is unavailable")
        return root

    def register(self, root_path):
        root = Path(root_path).expanduser().resolve()
        if not root.is_dir() or root == Path("/"):
            raise ValueError("Choose an existing folder, not the filesystem root")
        root_id = uuid4().hex
        self.roots[root_id] = root
        return root_id, root

    def restore(self, root_id, root_path):
        """Restore a persisted local workspace after an application restart."""
        root = Path(root_path).expanduser().resolve()
        if not root.is_dir() or root == Path("/"):
            raise ValueError("Workspace folder is no longer available")
        self.roots[root_id] = root
        return root

    @staticmethod
    def _denied(path):
        safe_env_templates = {".env.example", ".env.sample", ".env.template"}
        return any(part in {".aws", ".ssh", "secrets"} for part in path.parts) or path.name in SENSITIVE or \
            (path.name.startswith(".env") and path.name not in safe_env_templates) or path.suffix.lower() in {".pem", ".key"}

    def resolve(self, root_id, relative_path=".", write=False):
        root = self.root(root_id)
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("Workspace paths must be relative")
        resolved = (root / candidate).resolve(strict=False)
        if not resolved.is_relative_to(root) or self._denied(resolved.relative_to(root)):
            raise ValueError("Path is outside the approved workspace or is sensitive")
        if write and not resolved.parent.is_relative_to(root):
            raise ValueError("Invalid workspace write path")
        return resolved

    def mutable_path(self, root_id, relative_path):
        path = self.resolve(root_id, relative_path, write=True)
        if path == self.root(root_id):
            raise ValueError("The workspace root cannot be changed or deleted")
        return path

    def _ignored(self, relative, patterns):
        return any(part in IGNORED for part in relative.parts) or self._denied(relative) or any(
            fnmatch.fnmatch(str(relative), pattern.rstrip("/")) for pattern in patterns)

    async def list_files(self, root_id, relative_path="."):
        root, folder = self.root(root_id), self.resolve(root_id, relative_path)
        if not folder.is_dir():
            raise ValueError("Path is not a directory")
        patterns = self._ignore_patterns(root)
        def read():
            return [{"path": str(item.relative_to(root)), "name": item.name, "type": "directory" if item.is_dir() else "file",
                     "size_bytes": item.stat().st_size if item.is_file() else 0}
                    for item in sorted(folder.iterdir()) if not self._ignored(item.relative_to(root), patterns)]
        return await asyncio.to_thread(read)

    async def scan_files(self, root_id, limit=2_000):
        """Return metadata only; project source always remains on the local disk."""
        root, patterns = self.root(root_id), self._ignore_patterns(self.root(root_id))
        def scan():
            results = []
            for path in root.rglob("*"):
                relative = path.relative_to(root)
                if not path.is_file() or self._ignored(relative, patterns):
                    continue
                try:
                    data = path.read_bytes()
                except OSError:
                    continue
                results.append({"relative_path": str(relative), "language": self._language(path),
                                "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
                if len(results) >= limit:
                    break
            return results
        return await asyncio.to_thread(scan)

    async def read_file(self, root_id, relative_path, limit=200_000, offset_bytes=0):
        path = self.resolve(root_id, relative_path)
        if not path.exists():
            raise WorkspaceReadError("file_not_found", relative_path,
                f"File not found: {relative_path}. List its parent directory to find the correct path, or create it if the task requires a new file.", "list_parent_or_create")
        if not path.is_file():
            raise WorkspaceReadError("not_a_file", relative_path,
                f"Path is a directory, not a file: {relative_path}. Use workspace_list_directory to inspect it.", "workspace_list_directory")
        if not 4 <= limit <= 200_000 or offset_bytes < 0:
            raise ValueError("Invalid bounded read range")
        def read():
            with path.open("rb") as source:
                size = os.fstat(source.fileno()).st_size
                if offset_bytes > size:
                    raise WorkspaceReadError("read_offset_invalid", relative_path,
                        "Read offset exceeds the file size. Restart reading at offset_bytes=0.", "read_from_start")
                digest = hashlib.sha256()
                while chunk := source.read(65536): digest.update(chunk)
                source.seek(offset_bytes)
                data = source.read(limit)
            try:
                decoder = codecs.getincrementaldecoder("utf-8")()
                content = decoder.decode(data, final=offset_bytes + len(data) >= size)
            except UnicodeDecodeError as exc:
                raise WorkspaceReadError("not_utf8", relative_path,
                    "This range is not UTF-8 text. Inspect another source file; for paginated text use the returned next_offset_bytes boundary.", "inspect_text_file_or_read_boundary") from exc
            consumed = len(data) - len(decoder.getstate()[0])
            next_offset = offset_bytes + consumed
            return {"path": relative_path, "content": content, "sha256": digest.hexdigest(), "size_bytes": size,
                    "offset_bytes": offset_bytes, "next_offset_bytes": next_offset, "truncated": next_offset < size}
        return await asyncio.to_thread(read)

    async def write_file(self, root_id, relative_path, content, expected_sha256=None, create=False):
        root, path = self.root(root_id), self.resolve(root_id, relative_path, write=True)
        if path.exists() and create:
            raise WorkspaceFileExistsError("File already exists")
        before = path.read_bytes() if path.exists() else b""
        if expected_sha256 and hashlib.sha256(before).hexdigest() != expected_sha256:
            raise WorkspaceEditError('file_changed', relative_path,
                "File changed since it was read. Read the latest file, recompute the edit, and retry with that file’s current sha256. Never reuse an old hash or remove hash protection.", hashlib.sha256(before).hexdigest())
        if len(content.encode()) > 500_000:
            raise ValueError("Workspace file exceeds the write limit")
        snapshot = None
        if path.exists():
            snapshot_path = root / ".harness-trash" / "snapshots" / f"{uuid4().hex}-{path.name}"
            def save_snapshot():
                snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                snapshot_path.write_bytes(before)
            await asyncio.to_thread(save_snapshot)
            snapshot = str(snapshot_path.relative_to(root))
        def write():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        await asyncio.to_thread(write)
        return {"path": relative_path, "before_sha256": hashlib.sha256(before).hexdigest(),
                "after_sha256": hashlib.sha256(content.encode()).hexdigest(), "before_snapshot": snapshot, "bytes_written": len(content.encode()),
                "created": not bool(snapshot)}

    async def restore_snapshot(self, root_id, relative_path, snapshot_path, expected_sha256):
        root, target = self.root(root_id), self.mutable_path(root_id, relative_path)
        snapshot = (root / snapshot_path).resolve(strict=False)
        trash_root = (root / ".harness-trash").resolve(strict=False)
        if not snapshot.is_file() or not snapshot.is_relative_to(trash_root):
            raise ValueError("The original workspace snapshot is unavailable")
        current = target.read_bytes() if target.exists() else b""
        if hashlib.sha256(current).hexdigest() != expected_sha256:
            raise ValueError("File changed after this run; refusing to overwrite it")
        data = await asyncio.to_thread(snapshot.read_bytes)
        await asyncio.to_thread(target.write_bytes, data)
        return {"path": relative_path, "restored": True, "sha256": hashlib.sha256(data).hexdigest()}

    async def create_directory(self, root_id, relative_path):
        path = self.mutable_path(root_id, relative_path)
        if path.exists():
            if path.is_dir():
                return {"path": relative_path, "existed": True}
            raise ValueError("A file already exists at the requested directory path")
        await asyncio.to_thread(path.mkdir, parents=True)
        return {"path": relative_path, "existed": False}

    async def rename_path(self, root_id, relative_path, target_relative_path):
        source = self.mutable_path(root_id, relative_path)
        target = self.mutable_path(root_id, target_relative_path)
        if not source.exists() or target.exists():
            raise ValueError("Source is missing or destination already exists")
        before = hashlib.sha256(await asyncio.to_thread(source.read_bytes)).hexdigest() if source.is_file() else None
        await asyncio.to_thread(source.rename, target)
        return {"path": relative_path, "target_path": target_relative_path, "before_sha256": before, "after_sha256": before}

    async def delete_path(self, root_id, relative_path):
        root = self.root(root_id); source = self.mutable_path(root_id, relative_path)
        if not source.exists():
            raise ValueError("Path does not exist")
        before = hashlib.sha256(await asyncio.to_thread(source.read_bytes)).hexdigest() if source.is_file() else None
        trash = root / ".harness-trash" / uuid4().hex
        await asyncio.to_thread(trash.mkdir, parents=True, exist_ok=False)
        await asyncio.to_thread(shutil.move, str(source), str(trash / source.name))
        return {"path": relative_path, "trash_path": str((trash / source.name).relative_to(root)), "before_sha256": before, "after_sha256": None}

    async def search_text(self, root_id, query, relative_path="."):
        root = self.root(root_id); folder = self.resolve(root_id, relative_path); patterns = self._ignore_patterns(root)
        def search():
            results = []
            for path in folder.rglob("*"):
                relative = path.relative_to(root)
                if not path.is_file() or self._ignored(relative, patterns) or path.stat().st_size > 200_000:
                    continue
                try: lines = path.read_text(encoding="utf-8").splitlines()
                except UnicodeDecodeError: continue
                for number, line in enumerate(lines, 1):
                    if query.lower() in line.lower(): results.append({"path": str(relative), "line": number, "text": line[:300]})
                    if len(results) >= 100: return results
            return results
        return await asyncio.to_thread(search)

    async def run_command(self, root_id, command, cwd_relative=".", timeout=60):
        import shlex
        if any(token in command for token in (";", "|", "&&", "||", ">", "<", "`", "$(`")):
            raise WorkspaceCommandPolicyError("Shell chaining and redirection are not allowed")
        args = shlex.split(command)
        if not args or args[0] in BLOCKED_COMMANDS or not any(tuple(args[:len(prefix)]) == prefix for prefix in ALLOWED_COMMANDS):
            raise WorkspaceCommandPolicyError("Command is not allowed by workspace policy")
        cwd = self.resolve(root_id, cwd_relative)
        if not cwd.is_dir(): raise ValueError("Command directory does not exist")
        def run():
            process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, start_new_session=True,
                                       env={"PATH": os.environ.get("PATH", ""), "CI": "true", "npm_config_yes": "true", "NO_COLOR": "1"})
            try:
                stdout, stderr = process.communicate(timeout=min(timeout, 60))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                process.communicate()
                raise ValueError(f"Command timed out after {min(timeout, 60)} seconds")
            return {"exit_code": process.returncode, "stdout": stdout[-8000:], "stderr": stderr[-8000:]}
        return await asyncio.to_thread(run)

    @staticmethod
    def _ignore_patterns(root):
        patterns = []
        for filename in (".gitignore", ".workspaceignore"):
            path = root / filename
            if path.is_file():
                patterns.extend(line.strip().lstrip("/") for line in path.read_text(encoding="utf-8").splitlines()
                                if line.strip() and not line.lstrip().startswith("#") and not line.startswith("!"))
        return patterns

    @staticmethod
    def _language(path):
        return {".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
                ".jsx": "jsx", ".json": "json", ".css": "css", ".html": "html", ".md": "markdown",
                ".yml": "yaml", ".yaml": "yaml", ".sql": "sql"}.get(path.suffix.lower(), "text")
