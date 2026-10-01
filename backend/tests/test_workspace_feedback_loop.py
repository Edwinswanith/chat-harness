import asyncio
from pathlib import Path

from app.core.config import Settings
from app.harness.context_builder import ContextBuilder
from app.harness.finalizer import Finalizer
from app.harness.orchestrator import RunOrchestrator
from app.harness.planner import Planner
from app.memory.memory_service import MemoryService
from app.schemas.contracts import Decision
from app.tools.tool_orchestrator import ToolOrchestrator
from app.tools.tool_registry import ToolRegistry
from app.tools.workspace_tools import RunBuild, RunCommand, ListDirectory
from app.validation.validation_service import ValidationService
from app.workspaces.website_workflow import WebsiteWorkflow
from test_file_conflict_recovery import EmptyRag, setup


class ConflictModel:
    def __init__(self): self.calls = 0

    async def call(self, context):
        self.calls += 1
        if self.calls <= 5:
            return Decision(kind='tool', name='workspace_patch_file', arguments={
                'path': 'globals.css', 'find': 'black', 'replace': 'blue', 'expected_sha256': '0' * 64})
        latest = context.results[-1]
        if self.calls == 6:
            assert latest.status == 'success' and latest.data['content'] == 'body { color: black; }'
            assert any('file’s current sha256' in item or 'its current sha256' in item for item in context.feedback)
            return Decision(kind='tool', name='workspace_patch_file', arguments={
                'relative_path': 'globals.css', 'find': 'nonexistent text', 'replace': 'blue', 'expected_sha256': latest.data['sha256']})
        if self.calls == 7:
            assert latest.data['content'] == 'body { color: black; }'
            return Decision(kind='tool', name='workspace_patch_file', arguments={
                'relative_path': 'globals.css', 'find': 'black', 'replace': 'blue', 'expected_sha256': latest.data['sha256']})
        return Decision(kind='final', text='Updated the CSS successfully.')


async def execute(tmp_path, factory, prepare=None, max_steps=24, request_text=None):
    root, repo, repository, runs, scope, run, old_tools = await setup(tmp_path)
    service = old_tools.registry.get('workspace_patch_file', 'workspace').service
    if request_text:
        run = await repo.patch('run', run['id'], scope, request={**run['request'], 'text': request_text})
    if prepare: prepare(root)
    tools = ToolOrchestrator(ToolRegistry([*old_tools.registry.tools.values(), RunBuild(service), RunCommand(service), ListDirectory(service)]), repo, runs, workspace_max_calls=max_steps * 2)
    model = factory()
    orchestrator = RunOrchestrator(Planner(), ContextBuilder(), MemoryService(repo), EmptyRag(), model, tools,
        None, ValidationService(), Finalizer(repository, repo), runs, Settings(data_dir=tmp_path, workspace_max_steps=max_steps),
        WebsiteWorkflow(service, repo, runs.publisher, model))
    await orchestrator.run(run['id'], scope)
    return root, repo, runs, scope, await runs.get(run['id'], scope)


def test_stale_hashes_and_missing_patch_text_automatically_reread_and_repair(tmp_path):
    async def check():
        root, repo, runs, scope, run = await execute(tmp_path, ConflictModel)
        assert run['status'] == 'completed', run.get('error')
        assert (root / 'globals.css').read_text() == 'body { color: blue; }'
        calls = await repo.list('tool_run', scope)
        errors = [call for call in calls if call['status'] == 'error']
        assert len(errors) == 6
        assert [call['result']['data']['code'] for call in errors] == ['file_changed'] * 5 + ['patch_not_found']
        assert all(call['result']['retryable'] for call in errors)
        assert len([call for call in calls if call['name'] == 'workspace_read_file']) == 6
        assert len(await repo.list('workspace_change', scope)) == 1
        events = await runs.activity(run['id'], scope)
        assert len([event for event in events if event['event'] == 'feedback.retrying']) == 6
        assert not any(event['event'] == 'state' and event['data']['details']['status'] == 'failed' for event in events)
    asyncio.run(check())


class BuildModel:
    def __init__(self): self.calls = 0

    async def call(self, context):
        self.calls += 1
        if self.calls <= 4 or self.calls == 7:
            return Decision(kind='tool', name='workspace_run_build')
        if self.calls == 5:
            assert context.results[-1].data['exit_code'] == 1
            assert any('Build failed' in item or 'fixture build failure' in item for item in context.feedback)
            return Decision(kind='tool', name='workspace_read_file', arguments={'relative_path': 'check.cjs'})
        if self.calls == 6:
            return Decision(kind='tool', name='workspace_write_file', arguments={'relative_path': 'check.cjs',
                'content': 'console.log("build passed"); process.exit(0);', 'expected_sha256': context.results[-1].data['sha256']})
        return Decision(kind='final', text='Build passed after repair.')


def test_failed_commands_return_to_feedback_and_pass_after_more_than_three_failures(tmp_path):
    def prepare(root):
        (root / 'package.json').write_text('{"scripts":{"build":"node check.cjs"}}')
        (root / 'check.cjs').write_text('console.error("fixture build failure"); process.exit(1);')
    async def check():
        _, repo, runs, scope, run = await execute(tmp_path, BuildModel, prepare)
        assert run['status'] == 'completed', run.get('error')
        builds = [call for call in await repo.list('tool_run', scope) if call['name'] == 'workspace_run_build']
        assert [call['result']['data']['exit_code'] for call in builds] == [1, 1, 1, 1, 0]
        assert len([event for event in await runs.activity(run['id'], scope) if event['event'] == 'feedback.retrying']) == 4
    asyncio.run(check())


class PrematureModel(ConflictModel):
    async def call(self, context):
        if self.calls == 1:
            self.calls += 1
            return Decision(kind='final', text='Everything succeeded.')
        if self.calls == 2:
            assert any('Final response rejected' in item for item in context.feedback)
            self.calls = 6
        return await super().call(context)


def test_premature_final_is_feedback_instead_of_stopping_the_run(tmp_path):
    async def check():
        root, _, runs, scope, run = await execute(tmp_path, PrematureModel)
        assert run['status'] == 'completed', run.get('error')
        assert (root / 'globals.css').read_text() == 'body { color: blue; }'
        events = await runs.activity(run['id'], scope)
        assert len([event for event in events if event['event'] == 'final']) == 1
        assert any(event['event'] == 'feedback.retrying' and event['data']['details']['next_action'] == 'repair_unresolved_actions' for event in events)
    asyncio.run(check())


class TransientModel(ConflictModel):
    def __init__(self):
        super().__init__()
        self.failures = 2

    async def call(self, context):
        if self.failures:
            self.failures -= 1
            raise ConnectionError('Temporary model connection failure')
        return await super().call(context)


def test_model_request_errors_return_to_feedback_without_abandoning_task(tmp_path):
    async def check():
        _, _, runs, scope, run = await execute(tmp_path, TransientModel)
        assert run['status'] == 'completed', run.get('error')
        events = await runs.activity(run['id'], scope)
        retries = [event for event in events if event['event'] == 'feedback.retrying' and event['data']['details']['next_action'] == 'retry_model_request']
        assert len(retries) == 2
    asyncio.run(check())


def test_repair_continues_automatically_across_processing_and_tool_call_batches(tmp_path):
    async def check():
        root, repo, runs, scope, run = await execute(tmp_path, ConflictModel, max_steps=2)
        assert run['status'] == 'completed', run.get('error')
        assert (root / 'globals.css').read_text() == 'body { color: blue; }'
        assert run['execution_batch'] >= 3
        calls = await repo.list('tool_run', scope)
        assert all(call['result'].get('error') != 'Tool call limit reached' for call in calls)
        assert len({call['execution_batch'] for call in calls}) == 4
        events = await runs.activity(run['id'], scope)
        assert any(event['event'] == 'feedback.retrying' and event['data']['details']['next_action'] == 'continue_processing_batch' for event in events)
        assert not any(event['event'] == 'state' and event['data']['details']['status'] == 'failed' for event in events)
    asyncio.run(check())


class RepeatedSiteModel:
    def __init__(self): self.calls = 0

    async def call(self, context):
        self.calls += 1
        if self.calls in {1, 3}:
            return Decision(kind='tool', name='workspace_list_directory', arguments={'relative_path': '.'})
        if self.calls == 4:
            assert any('README.md' in feedback for feedback in context.feedback)
            return Decision(kind='tool', name='workspace_create_file', arguments={'relative_path': 'README.md', 'content': '# Meridian Studio\nBusiness portfolio. npm install; npm run build.'})
        return Decision(kind='tool', name='terminal_run_command', arguments={'command': 'npm run build'})

    async def visual_review(self, screenshots, brief):
        assert len(screenshots) == 2 and all(Path(path).stat().st_size > 1000 for path in screenshots)
        from test_website_completion import passing_review
        return passing_review()


def test_repeated_build_listing_loop_runs_completion_checks_and_repairs_before_final(tmp_path):
    from test_website_completion import website_files
    def prepare(root):
        for path, content in website_files().items():
            if path == 'README.md': continue
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        (root / 'node_modules').symlink_to(Path(__file__).parents[2] / 'frontend/node_modules', target_is_directory=True)
    async def check():
        _, _, runs, scope, run = await execute(tmp_path, RepeatedSiteModel, prepare, max_steps=2,
            request_text='Build a business portfolio website using React + Vite.')
        assert run['status'] == 'completed', run.get('error')
        assert run['website_validation']['passed'] and run['website_validation']['checks']['screenshot_review']
        assert run['execution_batch'] == 2
        events = await runs.activity(run['id'], scope)
        assert any(event['event'] == 'validation.failed' for event in events)
        assert any(event['event'] == 'validation.success' for event in events)
        assert len([event for event in events if event['event'] == 'final']) == 1
        assert not any(event['event'] == 'state' and event['data']['details']['status'] == 'failed' for event in events)
    asyncio.run(check())


def test_cancel_stops_a_workspace_run_that_is_continuing_batches(tmp_path):
    async def check():
        _, repo, repository, runs, scope, run, tools = await setup(tmp_path)
        service = tools.registry.get('workspace_patch_file', 'workspace').service
        class AlwaysMissing:
            async def call(self, context):
                return Decision(kind='tool', name='workspace_read_file', arguments={'relative_path': 'missing.jsx'})
        model = AlwaysMissing()
        orchestrator = RunOrchestrator(Planner(), ContextBuilder(), MemoryService(repo), EmptyRag(), model, tools,
            None, ValidationService(), Finalizer(repository, repo), runs, Settings(data_dir=tmp_path, workspace_max_steps=2),
            WebsiteWorkflow(service, repo, runs.publisher, model))
        task = asyncio.create_task(orchestrator.run(run['id'], scope))
        try:
            for _ in range(300):
                current = await runs.get(run['id'], scope)
                if current.get('execution_batch', 0) >= 1: break
                await asyncio.sleep(0.01)
            assert current.get('execution_batch', 0) >= 1
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert (await runs.get(run['id'], scope))['status'] == 'cancelled'
        assert not any(event['event'] == 'final' for event in await runs.activity(run['id'], scope))
    asyncio.run(check())


class RepeatedReadRecoveryModel:
    def __init__(self): self.calls = 0
    async def call(self, context):
        self.calls += 1
        if self.calls == 1:
            return Decision(kind='tool', name='workspace_patch_file', arguments={'relative_path':'globals.css', 'find':'missing text', 'replace':'blue'})
        if self.calls <= 5:
            return Decision(kind='tool', name='workspace_read_file', arguments={'relative_path':'globals.css'})
        if self.calls == 6:
            available = {tool['name'] for tool in context.tools}
            assert 'workspace_read_file' not in available and 'workspace_patch_file' in available
            assert any('Inspection cycle recovered' in message and 'failed actions remain unresolved' in message for message in context.feedback)
            latest = next(result for result in reversed(context.results) if result.data.get('sha256'))
            return Decision(kind='tool', name='workspace_patch_file', arguments={'relative_path':'globals.css', 'find':'black', 'replace':'blue', 'expected_sha256':latest.data['sha256']})
        assert 'workspace_read_file' in {tool['name'] for tool in context.tools}
        return Decision(kind='final', text='Updated the CSS and repaired the failed patch.')


def test_repeated_reads_recover_once_then_edit_across_batches(tmp_path):
    async def check():
        root, repo, runs, scope, run = await execute(tmp_path, RepeatedReadRecoveryModel, max_steps=2)
        assert run['status'] == 'completed', run.get('error')
        assert 'color: blue' in (root / 'globals.css').read_text()
        events = await runs.activity(run['id'], scope)
        recoveries = [e for e in events if e['event']=='feedback.retrying' and e['data']['details'].get('next_action')=='recover_inspection_cycle']
        assert len(recoveries) == 1
        calls = await repo.list('tool_run', scope)
        assert len([call for call in calls if call['name']=='workspace_read_file']) == 5
        assert not any('Repeated unchanged action detected.' in str(e['data']) for e in events)
    asyncio.run(check())


def test_repeat_detector_recognizes_new_file_versions_and_read_pages():
    from app.workspaces.progress import WorkspaceProgress
    from app.schemas.contracts import ToolResult
    progress = WorkspaceProgress()
    def read(sha): return ToolResult(status='success', data={'path':'app.jsx','sha256':sha,'content':sha})
    assert not progress.observe('workspace_read_file', {'path':'app.jsx'}, read('one'))
    assert not progress.observe('workspace_read_file', {'relative_path':'app.jsx'}, read('one'))
    assert progress.observe('workspace_read_file', {'relative_path':'app.jsx'}, read('one'))
    assert not progress.observe('workspace_read_file', {'relative_path':'app.jsx'}, read('two'))
    assert not progress.observe('workspace_read_file', {'relative_path':'app.jsx','offset_bytes':200000}, read('one'))


def test_invalid_mutation_arguments_do_not_leave_an_unrepairable_root_target():
    from app.workspaces.feedback_loop import WorkspaceFeedbackLoop
    from app.schemas.contracts import ToolResult
    loop = WorkspaceFeedbackLoop()
    loop.failed('workspace_patch_file', {}, ToolResult(status='error', error='Missing path', data={'code':'invalid_tool_arguments'}))
    loop.accepted('workspace_patch_file', {'relative_path':'src/App.jsx'}, ToolResult(status='success', data={'path':'src/App.jsx'}))
    assert loop.final_feedback() == ''


def test_build_failure_is_resolved_through_either_command_wrapper():
    from app.workspaces.feedback_loop import WorkspaceFeedbackLoop
    from app.schemas.contracts import ToolResult
    for failed_tool, args, success_tool, success_args in [
        ('workspace_run_build', {}, 'terminal_run_command', {'command':'npm run build'}),
        ('terminal_run_command', {'command':'npm run build'}, 'workspace_run_build', {})]:
        loop = WorkspaceFeedbackLoop()
        loop.failed(failed_tool, args, ToolResult(status='error', error='Build failed'))
        loop.accepted(success_tool, success_args, ToolResult(status='success', data={'exit_code':0}))
        assert loop.final_feedback() == ''


class BlockedCommandRecoveryModel:
    def __init__(self): self.calls=0
    async def call(self, context):
        self.calls += 1
        if self.calls==1: return Decision(kind='tool', name='terminal_run_command', arguments={'command':'find .'})
        if self.calls==2:
            assert context.results[-1].data['code']=='command_not_allowed'
            return Decision(kind='tool', name='workspace_run_build')
        return Decision(kind='final', text='Checked the project using the approved build command.')


def test_rejected_command_can_be_replaced_with_an_approved_check(tmp_path):
    def prepare(root):
        (root/'package.json').write_text('{"scripts":{"build":"node -e \\\"process.exit(0)\\\""}}')
    async def check():
        _, _, _, _, run = await execute(tmp_path, BlockedCommandRecoveryModel, prepare)
        assert run['status']=='completed', run.get('error')
    asyncio.run(check())


def test_website_import_failure_and_inspection_cycle_produce_targeted_repair(tmp_path):
    from test_website_completion import website_files, passing_review
    class Model:
        def __init__(self): self.calls=0
        async def call(self, context):
            self.calls += 1
            if self.calls in {1,6}: return Decision(kind='tool', name='workspace_run_build')
            if self.calls <= 4:
                return Decision(kind='tool', name='workspace_read_file', arguments={'relative_path':'src/components/Services.jsx'})
            if self.calls==5:
                assert 'workspace_read_file' not in {tool['name'] for tool in context.tools}
                assert any('Current project checks:' in message and 'Repair unresolved import ../../ui/SectionHeading' in message for message in context.feedback)
                current = next(result for result in reversed(context.results) if result.data.get('path')=='src/components/Services.jsx')
                return Decision(kind='tool', name='workspace_patch_file', arguments={'relative_path':'src/components/Services.jsx',
                    'find':'../../ui/SectionHeading','replace':'./ui/SectionHeading','expected_sha256':current.data['sha256']})
            return Decision(kind='final', text='Fixed the unresolved import and completed the requested website refinement.')
        async def visual_review(self, screenshots, brief): return passing_review()
    def prepare(root):
        files=website_files()
        files['src/components/Services.jsx'] = 'import Heading from "../../ui/SectionHeading";'+files['src/components/Services.jsx']
        for path, content in files.items():
            target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
        (root/'node_modules').symlink_to(Path(__file__).parents[2]/'frontend/node_modules',target_is_directory=True)
    async def check():
        root, _, runs, scope, run = await execute(tmp_path, Model, prepare, max_steps=2,
            request_text='Refine the existing React website in the selected workspace.')
        assert run['status']=='completed',run.get('error')
        assert not run['workspace_recovery_diagnostic']['passed']
        assert run['website_validation']['passed']
        assert '../../ui/SectionHeading' not in (root/'src/components/Services.jsx').read_text()
        events=await runs.activity(run['id'],scope)
        assert len([e for e in events if e['event']=='recovery.diagnostic'])==1
    asyncio.run(check())
