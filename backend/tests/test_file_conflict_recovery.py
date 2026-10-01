import asyncio
import hashlib

from app.core.config import Settings
from app.harness.context_builder import ContextBuilder
from app.harness.finalizer import Finalizer
from app.harness.orchestrator import RunOrchestrator
from app.harness.planner import Planner
from app.memory.memory_service import MemoryService
from app.repositories.database import Database
from app.repositories.entity_repository import EntityRepository
from app.repositories.run_repository import RunRepository
from app.schemas.contracts import Decision, MessageRequest, RagContext, Scope
from app.services.run_service import RunService
from app.tools.tool_orchestrator import ToolOrchestrator
from app.tools.tool_registry import ToolRegistry
from app.tools.workspace_tools import CreateFile, ReadFile, WriteFile, PatchFile
from app.validation.validation_service import ValidationService
from app.workspaces.provider import LocalWorkspaceProvider
from app.workspaces.service import WorkspaceService
from app.workspaces.website_workflow import WebsiteWorkflow


class EmptyRag:
    async def retrieve(self, *args):
        return RagContext()


async def setup(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'globals.css').write_text('body { color: black; }')
    db = Database(tmp_path / 'runs.db')
    repo = EntityRepository(db)
    repository = RunRepository(db, repo)
    runs = RunService(repository, repo)
    scope = Scope(user_id='test', workspace_id='test')
    workspace = WorkspaceService(repo, LocalWorkspaceProvider())
    selected = await workspace.create(scope, str(root))
    thread = await repo.create('thread', scope, '', title='Edit test')
    request = MessageRequest(thread_id=thread['id'], text='Edit the CSS file.', idempotency_key='edit')
    run = await repository.submit(scope, request)
    run = await repo.patch('run', run['id'], scope, mode='workspace', project_workspace_id=selected['id'])
    tools = ToolOrchestrator(ToolRegistry([CreateFile(workspace), ReadFile(workspace), WriteFile(workspace), PatchFile(workspace)]), repo, runs, workspace_max_calls=80)
    return root, repo, repository, runs, scope, run, tools


def test_existing_create_is_safe_and_identical_retries_are_noops(tmp_path):
    async def check():
        root, repo, _, runs, scope, run, tools = await setup(tmp_path)
        original = (root / 'globals.css').read_text()
        result = await tools.execute(scope, run, 'workspace_create_file', {'relative_path': 'globals.css', 'content': 'new styles'}, 0)
        assert result.status == 'error' and result.retryable
        assert result.data['code'] == 'file_exists'
        assert result.data['current_sha256'] == hashlib.sha256(original.encode()).hexdigest()
        assert 'expected_sha256' in result.error
        assert (root / 'globals.css').read_text() == original
        result = await tools.execute(scope, run, 'workspace_create_file', {'relative_path': 'globals.css', 'content': original}, 1)
        assert result.status == 'success' and result.data['operation'] == 'unchanged'
        assert not await repo.list('workspace_change', scope)
        events = await runs.activity(run['id'], scope)
        assert not any(event['event'] == 'workspace.file.created' for event in events)
        for path in ['../escape.css', '.env']:
            result = await tools.execute(scope, run, 'workspace_create_file', {'relative_path': path, 'content': 'unsafe'}, 2)
            assert result.status == 'error' and not result.retryable
    asyncio.run(check())


class RecoveryModel:
    def __init__(self, repeat=False, premature_final=False, paths=None):
        self.calls = 0
        self.repeat, self.premature_final = repeat, premature_final
        self.paths = paths or ['globals.css']

    async def call(self, context):
        phase = self.calls % 3
        path = self.paths[min(self.calls // 3, len(self.paths) - 1)]
        self.calls += 1
        if self.calls > len(self.paths) * 3 and not self.repeat:
            return Decision(kind='final', text='Updated the CSS.')
        if self.premature_final and self.calls >= 2:
            return Decision(kind='final', text='Done.')
        if phase == 0 or self.repeat:
            return Decision(kind='tool', name='workspace_create_file', arguments={'relative_path': path, 'content': 'body { color: blue; }'})
        assert any(path in message and 'workspace_read_file' in message for message in context.feedback)
        if phase == 1:
            assert context.results[-1].data['code'] == 'file_exists'
            return Decision(kind='tool', name='workspace_read_file', arguments={'relative_path': path})
        existing = context.results[-1].data
        return Decision(kind='tool', name='workspace_write_file', arguments={'relative_path': path, 'content': 'body { color: blue; }', 'expected_sha256': existing['sha256']})


async def run_model(tmp_path, model):
    root, repo, repository, runs, scope, run, tools = await setup(tmp_path)
    for path in model.paths[1:]:
        (root / path).write_text('body { color: black; }')
    orchestrator = RunOrchestrator(Planner(), ContextBuilder(), MemoryService(repo), EmptyRag(), model,
        tools, None, ValidationService(), Finalizer(repository, repo), runs, Settings(data_dir=tmp_path, workspace_max_steps=16, workspace_max_batches=1),
        WebsiteWorkflow(tools.registry.get('workspace_create_file', 'workspace').service, repo, runs.publisher, model))
    await orchestrator.run(run['id'], scope)
    return root, await runs.get(run['id'], scope), await runs.activity(run['id'], scope), repo, scope


def test_conflict_recovers_through_read_and_hash_checked_edit(tmp_path):
    async def check():
        root, run, events, repo, scope = await run_model(tmp_path, RecoveryModel(paths=['globals.css', 'tokens.css', 'layout.css', 'theme.css']))
        assert run['status'] == 'completed', run.get('error')
        assert all((root / path).read_text() == 'body { color: blue; }' for path in ['globals.css', 'tokens.css', 'layout.css', 'theme.css'])
        assert len([event for event in events if event['event'] == 'feedback.retrying']) == 4
        assert any(event['event'] == 'feedback.retrying' and 'already exists' in event['data']['details']['feedback'] for event in events)
        assert not any(event['event'] == 'commentary' and event['data']['component'] == 'feedback' for event in events)
        changes = await repo.list('workspace_change', scope)
        assert len(changes) == 4 and all(change['before_sha256'] and change['after_sha256'] for change in changes)
        failed = [record for record in await repo.list('tool_run', scope) if record['status'] == 'error']
        assert len(failed) == 4 and all(record['arguments']['content'] == '[redacted]' for record in failed)
    asyncio.run(check())


def test_repeated_conflicts_stop_at_bounded_limit_without_overwrite(tmp_path):
    async def check():
        root, run, events, _, _ = await run_model(tmp_path, RecoveryModel(repeat=True))
        assert run['status'] == 'failed' and 'run budget exhausted' in run['error']
        assert len([event for event in events if event['event'] == 'feedback.retrying']) == 16
        assert (root / 'globals.css').read_text() == 'body { color: black; }'
        assert not any(event['event'] == 'final' for event in events)
    asyncio.run(check())


def test_unresolved_conflict_cannot_claim_completion(tmp_path):
    async def check():
        _, run, events, _, _ = await run_model(tmp_path, RecoveryModel(premature_final=True))
        assert run['status'] == 'failed' and 'run budget exhausted' in run['error']
        assert not any(event['event'] == 'final' for event in events)
    asyncio.run(check())
