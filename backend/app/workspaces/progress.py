"""Detect repeated inspection/build actions and bound context between batches."""
import json
import hashlib

from app.schemas.contracts import ToolResult
from app.workspaces.feedback_loop import MUTATIONS


INSPECTIONS = {'workspace_read_file', 'workspace_list_directory', 'workspace_search_text'}


class WorkspaceProgress:
    def __init__(self):
        self.repeats = {}
        self.changed_paths = set()
        self.recovering = False

    def observe(self, name, arguments, result):
        data = result.data
        changed = name in MUTATIONS and data.get('operation') != 'unchanged' and (
            data.get('before_sha256') != data.get('after_sha256') or data.get('existed') is False
            or name in {'workspace_rename_path', 'workspace_delete_path'})
        if changed:
            self.repeats.clear()
            self.recovering = False
            if data.get('path'): self.changed_paths.add(data['path'])
            return False
        canonical = dict(arguments)
        if 'path' in canonical:
            canonical.setdefault('relative_path', canonical.pop('path'))
        if name == 'workspace_read_file':
            canonical.setdefault('offset_bytes', 0)
            canonical.setdefault('max_bytes', 200_000)
        # A fresh file version or a different read page is useful evidence.
        evidence = data if name in INSPECTIONS else None
        key = hashlib.sha256(json.dumps([name, canonical, evidence], sort_keys=True).encode()).hexdigest()
        if key not in self.repeats and len(self.repeats) >= 64:
            self.repeats.pop(next(iter(self.repeats)))
        self.repeats[key] = self.repeats.get(key, 0) + 1
        return self.repeats[key] >= 3 and not self.recovering

    def compact(self, context):
        # Original goal/plan stay intact; fresh reads remain available through tools.
        results = []
        seen = set()
        for result in reversed(context.results):
            data = dict(result.data)
            for field in ('stdout', 'stderr', 'stderr_tail'):
                if isinstance(data.get(field), str): data[field] = data[field][-3000:]
            item = ToolResult(**{**result.model_dump(), 'data': data})
            key = json.dumps(item.model_dump(), sort_keys=True)
            if key in seen: continue
            seen.add(key)
            results.append(item)
            if len(results) == 32: break
        context.results = list(reversed(results))
        context.feedback = list(dict.fromkeys(context.feedback))[-12:]
        context.feedback = [message[:8000] for message in context.feedback]
        context.feedback.append('Continue the original task in the existing workspace. Completed paths: '
                                + json.dumps(sorted(self.changed_paths)[-40:])
                                + '. Do not repeat unchanged listings or builds. Use completion-check feedback to repair missing work, '
                                'then request finalization. Read any file again if its current content/hash is needed.')
