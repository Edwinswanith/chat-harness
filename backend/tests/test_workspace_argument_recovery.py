import asyncio
import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.harness.context_builder import ContextBuilder
from app.harness.finalizer import Finalizer
from app.harness.orchestrator import RunOrchestrator
from app.harness.planner import Planner
from app.memory.memory_service import MemoryService
from app.model_clients.gemini_client import GeminiModelClient
from app.schemas.contracts import Decision
from app.tools.workspace_tools import PatchArguments
from app.validation.validation_service import ValidationService
from app.workspaces.website_workflow import WebsiteWorkflow
from test_file_conflict_recovery import EmptyRag, setup


@pytest.mark.parametrize('arguments', [
    {'path': 'globals.css'}, {'relative_path': 'globals.css'},
    {'path': 'globals.css', 'relative_path': 'globals.css'},
])
def test_patch_path_alias_keeps_the_canonical_schema(arguments):
    parsed = PatchArguments.model_validate({**arguments, 'find': 'black', 'replace': 'blue'})
    assert parsed.relative_path == 'globals.css'
    assert 'path' not in parsed.model_dump()
    schema = GeminiModelClient._gemini_schema(PatchArguments.model_json_schema())
    assert 'relative_path' in schema['properties'] and 'path' not in schema['properties']
    assert {'find', 'replace'}.issubset(schema['required'])
    from google.genai import types
    types.FunctionDeclaration(name='workspace_patch_file', parameters=schema)


def test_conflicting_aliases_and_unknown_fields_are_rejected():
    with pytest.raises(ValidationError, match='same target'):
        PatchArguments.model_validate({'path': 'first.css', 'relative_path': 'second.css', 'find': 'a', 'replace': 'b'})
    with pytest.raises(ValidationError):
        PatchArguments.model_validate({'path': 'globals.css', 'find': 'a', 'replace': 'b', 'unknown': True})


def test_alias_patch_changes_only_the_requested_file_and_logs_canonical_path(tmp_path):
    async def check():
        root, repo, _, runs, scope, run, tools = await setup(tmp_path)
        result = await tools.execute(scope, run, 'workspace_patch_file', {'path': 'globals.css', 'find': 'black', 'replace': 'blue'}, 0)
        assert result.status == 'success'
        assert (root / 'globals.css').read_text() == 'body { color: blue; }'
        record = (await repo.list('tool_run', scope))[0]
        assert record['arguments']['relative_path'] == 'globals.css' and 'path' not in record['arguments']
        events = await runs.activity(run['id'], scope)
        assert all(event['data']['details']['target'] == 'globals.css' for event in events if event['event'] in {'tool.started', 'tool'})
        for path in ['../escape', '.env']:
            blocked = await tools.execute(scope, run, 'workspace_patch_file', {'path': path, 'find': 'a', 'replace': 'b'}, 1)
            assert blocked.status == 'error' and not blocked.retryable
    asyncio.run(check())


def test_invalid_arguments_return_safe_guidance_without_mutation(tmp_path):
    async def check():
        root, repo, _, _, scope, run, tools = await setup(tmp_path)
        result = await tools.execute(scope, run, 'workspace_patch_file', {'path': 'globals.css', 'replace': 'secret-input-value'}, 0)
        assert result.status == 'error' and result.retryable
        assert result.data['code'] == 'invalid_tool_arguments'
        assert 'find' in result.error and 'relative_path' in result.data['allowed_fields']
        assert 'secret-input-value' not in result.error and 'pydantic.dev' not in result.error
        assert (root / 'globals.css').read_text() == 'body { color: black; }'
        assert not await repo.list('workspace_change', scope)
        assert 'secret-input-value' not in json.dumps(await repo.list('tool_run', scope))
    asyncio.run(check())


class ArgumentModel:
    def __init__(self, repeat=False, premature_final=False):
        self.calls = 0
        self.repeat, self.premature_final = repeat, premature_final

    async def call(self, context):
        self.calls += 1
        if self.calls == 1 or self.repeat:
            return Decision(kind='tool', name='workspace_patch_file', arguments={'path': 'globals.css', 'replace': 'blue'})
        assert any('Invalid arguments' in item and 'find' in item for item in context.feedback)
        if self.calls == 2 and not self.premature_final:
            assert context.results[-1].data['code'] == 'invalid_tool_arguments'
            return Decision(kind='tool', name='workspace_patch_file', arguments={'path': 'globals.css', 'find': 'black', 'replace': 'blue'})
        return Decision(kind='final', text='Updated the styles.')


@pytest.mark.parametrize('repeat,premature_final', [(False, False), (True, False), (False, True)])
def test_argument_errors_recover_and_cannot_loop_or_claim_false_completion(tmp_path, repeat, premature_final):
    async def check():
        root, repo, repository, runs, scope, run, tools = await setup(tmp_path)
        service = tools.registry.get('workspace_patch_file', 'workspace').service
        model = ArgumentModel(repeat, premature_final)
        orchestrator = RunOrchestrator(Planner(), ContextBuilder(), MemoryService(repo), EmptyRag(), model, tools,
            None, ValidationService(), Finalizer(repository, repo), runs, Settings(data_dir=tmp_path, workspace_max_steps=12, workspace_max_batches=1),
            WebsiteWorkflow(service, repo, runs.publisher, model))
        await orchestrator.run(run['id'], scope)
        result = await runs.get(run['id'], scope)
        events = await runs.activity(run['id'], scope)
        if repeat or premature_final:
            assert result['status'] == 'failed'
            assert 'run budget exhausted' in result['error']
            assert not any(event['event'] == 'final' for event in events)
            assert (root / 'globals.css').read_text() == 'body { color: black; }'
        else:
            assert result['status'] == 'completed', result.get('error')
            assert (root / 'globals.css').read_text() == 'body { color: blue; }'
        assert len([event for event in events if event['event'] == 'feedback.retrying']) == (12 if repeat or premature_final else 1)
    asyncio.run(check())
