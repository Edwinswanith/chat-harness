import asyncio
from pydantic import ValidationError
from time import monotonic
from datetime import datetime, timezone
from app.harness.execution_events import sanitize
from app.schemas.contracts import ToolResult
from app.workspaces.provider import WorkspaceEditError, WorkspaceReadError, WorkspaceCommandPolicyError


class ToolOrchestrator:
    def __init__(self, registry, repo, runs, max_calls=8, workspace_max_calls=24):
        self.registry, self.repo, self.runs = registry, repo, runs
        self.max_calls, self.workspace_max_calls = max_calls, workspace_max_calls

    def describe(self, mode=None):
        return self.registry.describe(mode)

    async def execute(self, scope, run, name, arguments, step):
        started = monotonic()
        start_timestamp = datetime.now(timezone.utc).isoformat()
        record = await self.repo.create("tool_run", scope, run["thread_id"],
            run_id=run["id"], name=name, step=step, execution_batch=run.get('execution_batch', 0), arguments=sanitize(arguments), status="running")
        publisher = self.runs.publisher
        log = {"tool_call_id": record["id"], "arguments": sanitize(arguments), "target": arguments.get("relative_path", arguments.get("path", arguments.get("cwd_relative", "."))), "start_timestamp": start_timestamp}
        await publisher.emit(run_id=run["id"], event_type="tool.started", component="terminal" if name.startswith("terminal_") else "tool", component_name=name, status="started", summary=name + " started", details=log)
        try:
            calls = [t for t in await self.repo.list("tool_run", scope, run["thread_id"])
                     if t["run_id"] == run["id"] and (run.get('mode') != 'workspace' or t.get('execution_batch', 0) == run.get('execution_batch', 0))]
            limit = self.workspace_max_calls if run.get("mode") == "workspace" else self.max_calls
            if len(calls) > limit:
                raise ValueError("Tool call limit reached")
            tool = self.registry.get(name, run.get("mode", "chatbot"))
            validated = tool.schema.model_validate(arguments)
            canonical_arguments = sanitize(validated.model_dump())
            log.update(arguments=canonical_arguments)
            await self.repo.patch("tool_run", record["id"], scope, arguments=canonical_arguments)
            result = await tool.execute(scope, {**run, "tool_run_id": record["id"]}, validated)
            if "exit_code" in result.data and result.data["exit_code"] != 0:
                result = ToolResult(status="error", data=result.data, error=result.data.get("stderr") or result.data.get("stderr_tail") or "Command failed", retryable=True)
        except asyncio.CancelledError:
            await self.repo.patch("tool_run", record["id"], scope, status="cancelled")
            await publisher.emit(run_id=run["id"], event_type="tool.cancelled", component="tool", component_name=name,
                                 status="cancelled", summary=name + " cancelled", duration_ms=int((monotonic()-started)*1000), details=log)
            raise
        except WorkspaceCommandPolicyError as exc:
            result = ToolResult(status='error', retryable=True, error=str(exc),
                data={'code': 'command_not_allowed', 'recovery': 'choose_approved_command'})
        except (WorkspaceEditError, WorkspaceReadError) as exc:
            result = ToolResult(status='error', retryable=True, error=str(exc),
                data={'code': exc.code, 'path': exc.path, 'recovery': exc.recovery,
                      'current_sha256': getattr(exc, 'current_sha256', None)})
        except ValidationError as exc:
            issues = [{"field": '.'.join(map(str, error['loc'])) or 'arguments', "type": error['type'], "message": error['msg']}
                      for error in exc.errors(include_url=False, include_input=False)]
            fields = list(tool.schema.model_fields)
            feedback = '; '.join(f"{issue['field']}: {issue['message']}" for issue in issues)
            result = ToolResult(status="error", retryable=True,
                error=f"Invalid arguments for {name}: {feedback}. Correct the arguments and retry. Allowed fields: {', '.join(fields)}.",
                data={"code": "invalid_tool_arguments", "tool": name, "issues": issues, "allowed_fields": fields,
                      "path": log['target'], "recovery": "correct_tool_arguments"})
        except (KeyError, ValueError, ArithmeticError, SyntaxError) as exc:
            result = ToolResult(status="error", error=str(exc), retryable=False)
        except Exception as exc:
            result = ToolResult(status="error", error=str(exc)[:500], retryable=True)
        await self.repo.patch("tool_run", record["id"], scope, status=result.status, result=sanitize(result.model_dump()), duration_ms=int((monotonic()-started)*1000))
        await publisher.emit(run_id=run["id"], event_type="tool", component="terminal" if name.startswith("terminal_") else "tool", component_name=name,
                             status="success" if result.status == "success" else "failed", summary=name + (" completed" if result.status == "success" else " failed") + ": " + str(log["target"]),
                             duration_ms=int((monotonic()-started)*1000), details={**log, "end_timestamp": datetime.now(timezone.utc).isoformat(), "name": name, **result.model_dump(), "next_action": result.data.get("recovery", "Validate result")})
        if (name.startswith("workspace_") or (name == "generate_image" and result.data.get("path"))) and result.status == "success":
            for change in await self.repo.list("workspace_change", scope):
                if change.get("run_id") == run["id"] and not change.get("tool_run_id"):
                    await self.repo.patch("workspace_change", change["id"], scope, tool_run_id=record["id"])
        if (name.startswith("workspace_") or (name == "generate_image" and result.data.get("path"))) and result.status == "success":
            data = result.data
            if data.get("path") or data.get("command"):
                await self.runs.event(run["id"], "workspace.activity", {"tool_run_id": record["id"], "tool": name,
                                      "path": data.get("path"), "command": data.get("command"), "status": data.get("status", "success")})
            file_events = {"generate_image": "workspace.file.created", "workspace_create_file": "workspace.file.created", "workspace_write_file": "workspace.file.modified",
                           "workspace_patch_file": "workspace.file.modified", "workspace_rename_path": "workspace.file.renamed",
                           "workspace_delete_path": "workspace.file.deleted"}
            if name in file_events and data.get("operation") != "unchanged":
                await self.runs.event(run["id"], file_events[name], {"tool_run_id": record["id"], "path": data.get("path"),
                                      "target_path": data.get("target_path"), "operation": data.get("operation"), "before_sha256": data.get("before_sha256"), "after_sha256": data.get("after_sha256"), "bytes_written": data.get("bytes_written")})
        return result
