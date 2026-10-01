import asyncio
import hashlib

import pytest

from app.core.config import Settings
from app.harness.context_builder import ContextBuilder
from app.harness.finalizer import Finalizer
from app.harness.orchestrator import RunOrchestrator
from app.harness.planner import Planner
from app.memory.memory_service import MemoryService
from app.repositories.run_repository import RunRepository
from app.schemas.contracts import Decision, MessageRequest
from app.services.run_service import RunService
from app.tools.tool_orchestrator import ToolOrchestrator
from app.tools.tool_registry import ToolRegistry
from app.tools.workspace_tools import CreateFile, ListDirectory, ReadFile, WriteFile
from app.validation.validation_service import ValidationService
from app.workspaces.continuation import prepare_continuation
from app.workspaces.provider import LocalWorkspaceProvider, WorkspaceReadError
from app.workspaces.service import WorkspaceService
from app.workspaces.website_workflow import WebsiteWorkflow
from test_file_conflict_recovery import setup, EmptyRag
from test_website_completion import harness


def test_paginated_unicode_reads_and_edits_preserve_the_entire_file(tmp_path):
    async def check():
        root, repo, _, _, scope, run, tools = await setup(tmp_path)
        text = 'abc🙂' * 40000 + '\nTAIL'
        (root / 'large.css').write_text(text)
        service = tools.registry.get('workspace_read_file', 'workspace').service
        offset, chunks = 0, []
        while True:
            result = await tools.execute(scope, run, 'workspace_read_file', {'relative_path': 'large.css', 'offset_bytes': offset}, offset)
            assert result.status == 'success'
            data = result.data
            assert len(data['content'].encode()) <= 200000
            assert data['sha256'] == hashlib.sha256(text.encode()).hexdigest()
            chunks.append(data['content'])
            if not data['truncated']: break
            assert data['next_offset_bytes'] > offset
            offset = data['next_offset_bytes']
        assert ''.join(chunks) == text
        await service.patch(scope, run['project_workspace_id'], 'large.css', 'TAIL', 'UPDATED', data['sha256'], run['id'])
        assert (root / 'large.css').read_text() == text.replace('TAIL', 'UPDATED')
        unchanged = await tools.execute(scope, run, 'workspace_create_file', {'relative_path': 'large.css', 'content': text.replace('TAIL', 'UPDATED')}, 4)
        assert unchanged.status == 'success' and unchanged.data['operation'] == 'unchanged'
        assert len(await repo.list('workspace_change', scope)) == 1
    asyncio.run(check())


def test_read_errors_are_specific_recoverable_and_security_stays_blocked(tmp_path):
    async def check():
        root, _, _, _, scope, run, tools = await setup(tmp_path)
        (root / 'components').mkdir()
        (root / 'binary.txt').write_bytes(b'\xff\xfe')
        for path, code in [('missing.jsx', 'file_not_found'), ('components', 'not_a_file'), ('binary.txt', 'not_utf8')]:
            result = await tools.execute(scope, run, 'workspace_read_file', {'relative_path': path}, 0)
            assert result.status == 'error' and result.retryable
            assert result.data['code'] == code and result.data['recovery']
        for path in ['../escape', '.env']:
            result = await tools.execute(scope, run, 'workspace_read_file', {'relative_path': path}, 1)
            assert result.status == 'error' and not result.retryable
        provider = LocalWorkspaceProvider({'root': root})
        with pytest.raises(WorkspaceReadError, match='offset exceeds'):
            await provider.read_file('root', 'globals.css', offset_bytes=1000)
    asyncio.run(check())


class ReadRecoveryModel:
    def __init__(self, repeat=False):
        self.calls, self.repeat = 0, repeat

    async def call(self, context):
        self.calls += 1
        if self.calls == 1 or self.repeat:
            return Decision(kind='tool', name='workspace_read_file', arguments={'relative_path': 'Testimonials.jsx'})
        assert any('File not found' in item for item in context.feedback)
        if self.calls == 2:
            return Decision(kind='tool', name='workspace_list_directory', arguments={'relative_path': '.'})
        if self.calls == 3:
            return Decision(kind='tool', name='workspace_create_file', arguments={'relative_path': 'Testimonials.jsx', 'content': 'export default () => null;'})
        return Decision(kind='final', text='Created the missing component.')


async def execute(repo, repository, runs, scope, run, service, model, tmp_path):
    tools = ToolOrchestrator(ToolRegistry([CreateFile(service), ReadFile(service), WriteFile(service), ListDirectory(service)]), repo, runs, workspace_max_calls=80)
    orchestrator = RunOrchestrator(Planner(), ContextBuilder(), MemoryService(repo), EmptyRag(), model,
        tools, None, ValidationService(), Finalizer(repository, repo), runs, Settings(data_dir=tmp_path, workspace_max_steps=12, workspace_max_batches=1),
        WebsiteWorkflow(service, repo, runs.publisher, model))
    await orchestrator.run(run['id'], scope)
    return await runs.get(run['id'], scope)


@pytest.mark.parametrize('repeat', [False, True])
def test_missing_read_recovers_or_stops_at_a_bounded_limit(tmp_path, repeat):
    async def check():
        root, repo, repository, runs, scope, run, tools = await setup(tmp_path)
        service = tools.registry.get('workspace_read_file', 'workspace').service
        result = await execute(repo, repository, runs, scope, run, service, ReadRecoveryModel(repeat), tmp_path)
        assert result['status'] == ('failed' if repeat else 'completed'), result.get('error')
        if repeat:
            assert 'run budget exhausted' in result['error']
            events = await runs.activity(run['id'], scope)
            assert len([event for event in events if event['event'] == 'feedback.retrying']) == 12
        else:
            assert (root / 'Testimonials.jsx').is_file()
    asyncio.run(check())


def test_continue_resumes_original_goal_and_preserves_existing_work(tmp_path):
    async def check():
        root, repo, repository, runs, scope, run, tools = await setup(tmp_path)
        service = tools.registry.get('workspace_read_file', 'workspace').service
        await tools.execute(scope, run, 'workspace_create_file', {'relative_path': 'completed.txt', 'content': 'keep this work'}, 0)
        await repo.patch('run', run['id'], scope, status='failed', error='File not found: Testimonials.jsx')
        request = MessageRequest(thread_id=run['thread_id'], text='continue', idempotency_key='continue')
        new = await repository.submit(scope, request)
        new = await repo.patch('run', new['id'], scope, mode='workspace', project_workspace_id=run['project_workspace_id'])
        result = await execute(repo, repository, runs, scope, new, service, ReadRecoveryModel(), tmp_path)
        assert result['status'] == 'completed', result.get('error')
        assert result['request']['text'] == 'continue'
        assert result['task_request']['text'] == 'Edit the CSS file.'
        assert result['continuation']['run_id'] == run['id']
        assert result['continuation']['actions'][0]['path'] == 'completed.txt'
        assert (root / 'completed.txt').read_text() == 'keep this work'
        events = await runs.activity(new['id'], scope)
        assert any(event['event'] == 'commentary' and 'continue the previous task' in event['data']['details']['text'] for event in events)
        assert (await runs.get(run['id'], scope))['status'] == 'failed'
    asyncio.run(check())


def test_continued_website_keeps_plan_and_cannot_skip_validation(tmp_path):
    async def check():
        old, _, _, repo, scope = await harness(tmp_path, {'src/App.jsx': 'export default () => <h1>Hero</h1>'}, max_steps=12)
        assert old['status'] == 'failed'
        repository = RunRepository(repo.db, repo)
        runs = RunService(repository, repo)
        service = WorkspaceService(repo, LocalWorkspaceProvider())
        new = await repository.submit(scope, MessageRequest(thread_id=old['thread_id'], text='continue', idempotency_key='resume-site'))
        new = await repo.patch('run', new['id'], scope, mode='workspace', project_workspace_id=old['project_workspace_id'])
        class FinalOnly:
            async def call(self, context):
                assert context.request['text'] == old['request']['text']
                assert 'Previous run evidence' in context.plan
                return Decision(kind='final', text='Done.')
        result = await execute(repo, repository, runs, scope, new, service, FinalOnly(), tmp_path)
        assert result['status'] == 'failed' and result['task_classification']['requires_full_project']
        assert result['implementation_plan'] == old['implementation_plan']
        assert result['design_brief'] == old['design_brief']
        assert not result['website_validation']['passed']
        assert not any(event['event'] == 'final' for event in await runs.activity(new['id'], scope))
    asyncio.run(check())


@pytest.mark.parametrize('status,other_workspace', [('completed', False), ('failed', True)])
def test_continue_does_not_resume_completed_or_other_workspace_tasks(tmp_path, status, other_workspace):
    async def check():
        _, repo, repository, _, scope, old, _ = await setup(tmp_path)
        await repo.patch('run', old['id'], scope, status=status)
        new = await repository.submit(scope, MessageRequest(thread_id=old['thread_id'], text='continue', idempotency_key='resume'))
        new = await repo.patch('run', new['id'], scope, mode='workspace', project_workspace_id='other' if other_workspace else old['project_workspace_id'])
        result, context = await prepare_continuation(repo, scope, new)
        assert not context and 'continuation' not in result
    asyncio.run(check())
