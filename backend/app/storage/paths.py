from pathlib import Path


def _filename(name):
    return Path(name).name.replace(" ", "-") or "upload"


def file_key(file_id, derived=False, scope=None, thread_id=None, name="upload"):
    if scope and thread_id:
        prefix = f"workspaces/{scope.workspace_id}/threads/{thread_id}/files/{file_id}"
        return f"{prefix}/derived/extracted.md" if derived else f"{prefix}/original/{_filename(name)}"
    return f"files/{file_id}/" + ("extracted.md" if derived else "original")


def artifact_key(artifact_id, name, scope=None, thread_id=None):
    if scope and thread_id:
        return f"workspaces/{scope.workspace_id}/threads/{thread_id}/artifacts/{artifact_id}/original/{_filename(name)}"
    return f"artifacts/{artifact_id}/{_filename(name)}"
