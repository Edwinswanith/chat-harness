"""One sanitized event schema for durable storage and streaming."""
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

_SECRET = re.compile(r"api[_-]?key|secret|password|authorization|cookie|credential|(?:^|_)token$|mongodb_uri|session", re.I)
_VALUE = re.compile(r"""(?i)(bearer\s+)[\w.\-]+|((?:api[_-]?key|password|secret(?:_access_key)?|token|access_key_id)\s*["']?\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)|((?:mongodb(?:\+srv)?|https?)://)[^\s/@]+:[^\s/@]+@""")


def sanitize(value):
    if isinstance(value, dict):
        sensitive_file = bool(re.search(r"(?:^|/)\.env(?:\.|$)", str(value.get('path', value.get('relative_path', '')))))
        return {str(key): ('[redacted]' if _SECRET.search(str(key)) or str(key) in {'content', 'find', 'replace', 'before_snapshot', 'system_prompt', 'prompt'} or (sensitive_file and str(key) in {'stdout', 'text', 'result'}) else sanitize(item)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return _VALUE.sub(lambda match: (match.group(1) or match.group(2) or match.group(3)) + '[redacted]', value)
    return value


def envelope(event, data, run=None):
    data, run = sanitize(data or {}), run or {}
    stage = data.get('status', '')
    component = data.get('component') or event.split('.')[0]
    if event in {'state', 'final', 'delta'}: component = 'orchestrator'
    if component == 'design': component = 'planner'
    if component == 'build': component = 'terminal'
    if component == 'visual_validation': component = 'visual_qa'
    summaries = {'created': 'Run created', 'planning': 'Creating implementation plan', 'context_building': 'Building request context', 'inspecting_workspace': 'Inspecting selected workspace', 'designing': 'Creating website design system', 'coding': 'Implementing planned project', 'model_running': 'Requesting next model action', 'tool_running': 'Executing tool action', 'validating': 'Validating action result', 'building': 'Checking project and running build', 'rendering': 'Loading preview and capturing screenshots', 'visual_validating': 'Reviewing desktop and mobile layouts', 'repairing': 'Repairing validation failures', 'final_review': 'Checking completion contract', 'completed': 'Run completed', 'failed': 'Run failed', 'cancelled': 'Run cancelled'}
    status = data.get('event_status') or ('success' if event.endswith(('.completed', '.passed')) or stage in {'success', 'completed'} else 'failed' if event.endswith('.failed') or stage in {'failed', 'error'} else 'cancelled' if stage == 'cancelled' else 'started' if event.endswith('.started') else 'queued' if stage == 'created' else 'running')
    return {'event_id': 'evt_' + uuid4().hex, 'timestamp': datetime.now(timezone.utc).isoformat(),
            'workspace_id': run.get('project_workspace_id') or run.get('workspace_id'), 'conversation_id': run.get('thread_id'), 'run_id': run.get('id') or data.get('run_id'), 'parent_run_id': run.get('parent_run_id'),
            'component': component, 'component_name': data.get('component_name') or data.get('name') or component,
            'event_type': data.get('event_type') or ('orchestrator.stage' if event == 'state' else event), 'status': status,
            'summary': data.get('summary') or summaries.get(stage) or event.replace('.', ' ').replace('_', ' ').capitalize(),
            'duration_ms': data.get('duration_ms', 0), 'details': data}


class ExecutionEventPublisher:
    def __init__(self, repository): self.repository = repository

    async def emit(self, *, run_id, event_type, component, component_name=None, status='success', summary, duration_ms=0, details=None, **identity):
        await self.repository.event(run_id, event_type, {**(details or {}), **identity, 'component': component,
            'component_name': component_name or component, 'event_status': status, 'summary': summary, 'duration_ms': duration_ms})

    @asynccontextmanager
    async def action(self, run_id, component, name, summary, details=None):
        started = monotonic()
        result = {}
        await self.emit(run_id=run_id, event_type=f'{component}.started', component=component, component_name=name,
                        status='started', summary=summary, details=details)
        try:
            yield result
        except BaseException as exc:
            await self.emit(run_id=run_id, event_type=f'{component}.failed', component=component, component_name=name,
                            status='cancelled' if type(exc).__name__ == 'CancelledError' else 'failed', summary=summary + ' failed', duration_ms=int((monotonic()-started)*1000), details={**(details or {}), 'error': str(exc)})
            raise
        else:
            failed = result.get('passed') is False or result.get('result_status') == 'error'
            await self.emit(run_id=run_id, event_type=f'{component}.failed' if failed else f'{component}.completed', component=component, component_name=name, status='failed' if failed else 'success',
                            summary=result.pop('summary', summary + (' failed' if failed else ' completed')), duration_ms=int((monotonic()-started)*1000), details={**(details or {}), **result})
