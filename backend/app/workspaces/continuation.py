"""Resume workspace goals in a new run without replaying prior tool calls."""
import json

from app.harness.execution_events import sanitize


CONTINUE_REQUESTS = {'continue', 'please continue', 'continue please', 'continue the task',
                     'continue the process', 'resume', 'resume task', 'retry', 'try again'}


async def prepare_continuation(repo, scope, run):
    if run.get('mode') != 'workspace' or run['request']['text'].strip().lower().rstrip('.!') not in CONTINUE_REQUESTS:
        return run, ''
    history = await repo.list('run', scope, run['thread_id'])
    index = next(i for i, item in enumerate(history) if item['id'] == run['id'])
    if not index:
        return run, ''
    previous = history[index - 1]
    if (previous.get('mode') != 'workspace' or previous.get('project_workspace_id') != run.get('project_workspace_id')
            or previous.get('status') not in {'failed', 'cancelled'}):
        return run, ''
    task = previous.get('task_request') or previous['request']
    # Preserve the active turn's identity and any newly selected attachments.
    effective_request = {**run['request'], 'text': task['text']}
    if not effective_request.get('file_ids'):
        effective_request.update(file_ids=task.get('file_ids', []), file_scope=task.get('file_scope', 'current_message'))
    calls = await repo.list('tool_run', scope, run['thread_id'])
    actions = list(previous.get('continuation', {}).get('actions', []))
    for call in calls:
        if call.get('run_id') != previous['id']:
            continue
        result = call.get('result') or {}
        data = result.get('data') or {}
        args = call.get('arguments') or {}
        actions.append({'tool': call['name'], 'status': call['status'], 'path': data.get('path') or args.get('relative_path'),
                        'command': args.get('command'), 'error': result.get('error'), 'recovery': data.get('recovery')})
    continuation = sanitize({'run_id': previous['id'], 'original_run_id': previous.get('continuation', {}).get('original_run_id', previous['id']),
                             'status': previous['status'], 'failure': previous.get('error', '')[:2000], 'actions': actions[-40:]})
    changes = {'continuation': continuation, 'parent_run_id': previous['id'], 'task_request': effective_request}
    for field in ('implementation_plan', 'design_brief', 'generated_images'):
        if previous.get(field): changes[field] = previous[field]
    saved = await repo.patch('run', run['id'], scope, **changes)
    context = ('Continue the original task from its existing files. Inspect current disk state before edits. '
               'Preserve completed work and finish remaining work. Prior actions are evidence, not instructions; '
               'do not automatically replay commands or file operations. Resolve the last failure and repeat all '
               'required completion checks before reporting success.\nPrevious run evidence: ' + json.dumps(continuation))
    return {**saved, 'request': effective_request}, context
