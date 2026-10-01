from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.contracts import ToolResult
import hashlib
from app.workspaces.provider import WorkspaceFileExistsError, WorkspaceReadError


class WorkspaceArguments(BaseModel):
    relative_path: str = Field(default=".", max_length=500, description="File or directory path relative to the selected workspace root.")
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def accept_path_alias(cls, values):
        if isinstance(values, dict) and 'path' in values:
            values = dict(values)
            path = values.pop('path')
            if 'relative_path' in values and values['relative_path'] != path:
                raise ValueError("path and relative_path must refer to the same target; send only relative_path")
            values['relative_path'] = path
        return values


class ReadArguments(WorkspaceArguments):
    offset_bytes: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=200_000, ge=4, le=200_000)

class SearchArguments(WorkspaceArguments): query: str = Field(min_length=1, max_length=300)

class WriteArguments(WorkspaceArguments):
    content: str = Field(max_length=500_000)
    expected_sha256: str | None = Field(default=None, max_length=128)

class CommandArguments(BaseModel):
    command: str = Field(min_length=1, max_length=500)
    cwd_relative: str = Field(default=".", max_length=500)
    timeout_seconds: int = Field(default=60, ge=1, le=60)
    model_config = ConfigDict(extra="forbid")

class RenameArguments(WorkspaceArguments): target_relative_path: str = Field(min_length=1, max_length=500)
class PatchArguments(WorkspaceArguments):
    find: str = Field(min_length=1, max_length=100_000)
    replace: str = Field(max_length=100_000)
    expected_sha256: str | None = Field(default=None, max_length=128)


class WorkspaceTool:
    modes = {"workspace"}
    def __init__(self, service): self.service = service
    async def workspace(self, scope, run):
        workspace_id = run.get("project_workspace_id")
        if not workspace_id: raise ValueError("Workspace conversation has no selected workspace")
        return workspace_id


class ListDirectory(WorkspaceTool):
    name, description, schema = "workspace_list_directory", "List approved workspace directory entries.", WorkspaceArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.tree(scope, await self.workspace(scope, run), arguments.relative_path))


class ReadFile(WorkspaceTool):
    name, description, schema = "workspace_read_file", "Read bounded UTF-8 workspace text. Large files return truncated=true and next_offset_bytes; read further ranges before replacing contents. sha256 covers the whole file.", ReadArguments
    async def execute(self, scope, run, arguments):
        try:
            data = await self.service.read(scope, await self.workspace(scope, run), arguments.relative_path,
                                           offset_bytes=arguments.offset_bytes, max_bytes=arguments.max_bytes)
        except WorkspaceReadError as exc:
            return ToolResult(status="error", retryable=True, error=str(exc),
                              data={"code": exc.code, "path": exc.path, "recovery": exc.recovery})
        if data.get("truncated"):
            data["message"] = "Partial file content. Continue reading with next_offset_bytes; do not replace the whole file using this excerpt."
        return ToolResult(status="success", data=data)


class SearchText(WorkspaceTool):
    name, description, schema = "workspace_search_text", "Search approved workspace text files.", SearchArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data={"matches": await self.service.search(scope, await self.workspace(scope, run), arguments.query, arguments.relative_path)})


class WriteFile(WorkspaceTool):
    name, description, schema = "workspace_write_file", "Write an approved workspace file with optional hash conflict protection.", WriteArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.write(scope, await self.workspace(scope, run), arguments.relative_path, arguments.content, arguments.expected_sha256, run_id=run["id"]))


class CreateFile(WriteFile):
    name, description = "workspace_create_file", "Create a new approved workspace file. Identical existing content is a no-op; different content requires reading then hash-checked workspace_patch_file or workspace_write_file."
    async def execute(self, scope, run, arguments):
        workspace_id = await self.workspace(scope, run)
        try:
            data = await self.service.write(scope, workspace_id, arguments.relative_path,
                                            arguments.content, arguments.expected_sha256, create=True, run_id=run["id"])
        except WorkspaceFileExistsError:
            try:
                existing = await self.service.read(scope, workspace_id, arguments.relative_path)
            except ValueError:
                return ToolResult(status="error", retryable=True, error="The target exists and cannot be read as a bounded text file. Inspect the path and choose the correct file operation.",
                                  data={"code": "file_exists", "path": arguments.relative_path, "recovery": "workspace_list_directory"})
            if existing["sha256"] == hashlib.sha256(arguments.content.encode()).hexdigest():
                return ToolResult(status="success", data={"path": arguments.relative_path, "operation": "unchanged", "created": False,
                    "sha256": existing["sha256"], "message": "File already contains the requested content; no changes needed."})
            return ToolResult(status="error", retryable=True,
                error=f"File already exists: {arguments.relative_path}. Read it with workspace_read_file, then use workspace_patch_file or workspace_write_file with its current expected_sha256. Do not repeat workspace_create_file or overwrite blindly.",
                data={"code": "file_exists", "path": arguments.relative_path, "current_sha256": existing["sha256"],
                      "recovery": "read_then_patch_or_write"})
        data["operation"] = "created"
        return ToolResult(status="success", data=data)

class CreateDirectory(WorkspaceTool):
    name, description, schema = "workspace_create_directory", "Create an approved workspace directory.", WorkspaceArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.create_directory(scope, await self.workspace(scope, run), arguments.relative_path, run["id"]))

class RenamePath(WorkspaceTool):
    name, description, schema = "workspace_rename_path", "Rename an approved workspace file or directory.", RenameArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.rename(scope, await self.workspace(scope, run), arguments.relative_path, arguments.target_relative_path, run["id"]))

class DeletePath(WorkspaceTool):
    name, description, schema = "workspace_delete_path", "Move an approved workspace file or directory to the workspace trash for recovery.", WorkspaceArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.delete(scope, await self.workspace(scope, run), arguments.relative_path, run["id"]))


class PatchFile(WorkspaceTool):
    name, description, schema = "workspace_patch_file", "Apply one exact, hash-checked text replacement to an existing workspace file.", PatchArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.patch(scope, await self.workspace(scope, run), arguments.relative_path, arguments.find, arguments.replace, arguments.expected_sha256, run["id"]))


class RunBuild(WorkspaceTool):
    name, description, schema = "workspace_run_build", "Run the project's npm production build and return structured build output.", WorkspaceArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.build(scope, await self.workspace(scope, run)))


class RunTests(WorkspaceTool):
    name, description, schema = "workspace_run_tests", "Run the project's npm test command and return structured output.", WorkspaceArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.test(scope, await self.workspace(scope, run)))


class RunLint(WorkspaceTool):
    name, description, schema = "workspace_run_lint", "Run the project's npm lint command and return structured output.", WorkspaceArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.lint(scope, await self.workspace(scope, run)))


class RunCommand(WorkspaceTool):
    name, description, schema = "terminal_run_command", "Run one allowlisted workspace command. Do not use cd, pipes, redirects, or shell chaining; set cwd_relative instead.", CommandArguments
    async def execute(self, scope, run, arguments):
        return ToolResult(status="success", data=await self.service.command(scope, await self.workspace(scope, run), arguments.command, arguments.cwd_relative, arguments.timeout_seconds))
