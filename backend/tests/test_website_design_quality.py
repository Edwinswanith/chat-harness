import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.core.container import AppContainer
from app.main import create_app
from app.model_clients.gemini_client import GeminiModelClient
from app.schemas.contracts import MessageRequest, Scope, ModelContext, MemoryBundle, RagContext
from app.tools.generate_image import GenerateImage, ImageArguments
from app.workspaces.website_workflow import WebsiteWorkflow
from test_file_conflict_recovery import setup


def test_visual_refinement_gets_persisted_brief_before_coding(tmp_path):
    async def check():
        root, repo, _, runs, scope, run, tools = await setup(tmp_path)
        service = tools.registry.get('workspace_create_file').service
        (root / 'package.json').write_text('{"dependencies":{"react":"*"}}')
        run = {**run, 'request': {**run['request'], 'text': 'Change the button color'}}
        classified, context = await WebsiteWorkflow(service, repo, runs.publisher).prepare(scope, run)
        saved = await repo.get('run', run['id'], scope)
        assert classified['requires_design_agent'] and not classified['requires_full_project']
        assert saved['design_brief']['project_type'] == 'visual_refinement'
        assert 'only the requested visual refinement' in context
    asyncio.run(check())


def test_generated_assets_stay_in_selected_root_without_overwrites(tmp_path):
    class Images:
        calls = 0
        async def generate(self, prompt):
            self.calls += 1
            return 'generated.png', b'\x89PNG\r\n\x1a\nfixture'
    async def check():
        root, repo, _, _, scope, run, tools = await setup(tmp_path)
        images = Images()
        tool = GenerateImage(images, None, tools.registry.get('workspace_create_file').service)
        args = ImageArguments(prompt='Architectural brand artwork', relative_path='src/assets/hero.png')
        result = await tool.execute(scope, run, args)
        assert result.status == 'success' and (root / 'src/assets/hero.png').read_bytes().startswith(b'\x89PNG')
        assert result.data['after_sha256']
        for path in ('src/assets/hero.png', '../escape.png', '.ssh/key.png', '/tmp/escape.png'):
            with pytest.raises(ValueError):
                await tool.execute(scope, run, ImageArguments(prompt='Another image', relative_path=path))
        assert images.calls == 1
        assert any(change['path'] == 'src/assets/hero.png' for change in await repo.list('workspace_change', scope))
    asyncio.run(check())


def test_optional_asset_path_has_valid_gemini_schema():
    from google.genai import types
    schema = GeminiModelClient._gemini_schema(ImageArguments.model_json_schema())
    assert schema['properties']['relative_path']['type'] == 'string'
    assert schema['properties']['relative_path']['nullable'] is True
    types.FunctionDeclaration(name='generate_image', parameters=schema)


def test_repair_model_receives_actual_screenshot_bytes(tmp_path):
    desktop = tmp_path / 'desktop.png'; desktop.write_bytes(b'actual pixels')
    captured = {}
    def generate_content(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(candidates=[], text='Ready for validation', usage_metadata=None)
    model = GeminiModelClient('key', 'model')
    model._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    context = ModelContext(request={'text': 'Build portfolio', 'mode': 'workspace', 'repair_screenshots': [str(desktop)]},
        plan='Design and repair', memory=MemoryBundle(), rag=RagContext())
    model._call_sync(context)
    assert captured['contents'][-1].inline_data.data == b'actual pixels'


def test_screenshot_endpoint_enforces_scope_workspace_and_path_boundary(tmp_path):
    async def check():
        container = AppContainer(Settings(data_dir=tmp_path / 'data', tokens={'alice': ['alice', 'workspace'], 'bob': ['bob', 'workspace']}))
        auth = Scope(user_id='alice', workspace_id='workspace')
        root = tmp_path / 'site'; root.mkdir()
        workspace = await container.workspaces.create(auth, str(root))
        thread = await container.chat.create_thread(auth, mode='workspace', project_workspace_id=workspace['id'])
        run = await container.run_service.repository.submit(auth, MessageRequest(thread_id=thread['id'], text='Build a site', idempotency_key='preview'))
        await container.repo.patch('run', run['id'], auth, mode='workspace', project_workspace_id=workspace['id'])
        output = root / '.harness-preview'; output.mkdir()
        (output / f"{run['id']}-desktop.png").write_bytes(b'preview pixels')
        url = f"/api/workspaces/{workspace['id']}/runs/{run['id']}/preview/desktop"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(container)), base_url='http://test') as client:
            assert (await client.get(url)).status_code == 401
            assert (await client.get(url, headers={'Authorization':'Bearer bob'})).status_code == 404
            response = await client.get(url, headers={'Authorization':'Bearer alice'})
            assert response.status_code == 200 and response.content == b'preview pixels'
            assert response.headers['content-type'] == 'image/png'
            outside = tmp_path / 'private.png'; outside.write_bytes(b'private')
            (output / f"{run['id']}-mobile.png").symlink_to(outside)
            assert (await client.get(url.replace('/desktop', '/mobile'), headers={'Authorization':'Bearer alice'})).status_code == 404
            assert (await client.get(url.replace('/desktop', '/unknown'), headers={'Authorization':'Bearer alice'})).status_code == 404
    asyncio.run(check())
