import asyncio
from types import SimpleNamespace

from app.core.config import Settings
from app.harness.context_builder import ContextBuilder
from app.harness.finalizer import Finalizer
from app.harness.orchestrator import RunOrchestrator
from app.harness.planner import Planner
from app.memory.memory_service import MemoryService
from app.schemas.contracts import Decision, SubAgentResult
from app.subagents.manager import SubAgentManager
from app.tools.generate_image import GenerateImage
from app.validation.validation_service import ValidationService
from app.workspaces.image_integration import integration_feedback
from app.workspaces.website_workflow import WebsiteWorkflow
from test_file_conflict_recovery import setup, EmptyRag


class Images:
    async def generate(self, prompt): return 'logo.png', b'\x89PNG\r\n\x1a\nfixture'


def test_default_generated_logo_saved_and_integrated_before_final(tmp_path):
    async def check():
        root, repo, repository, runs, scope, run, tools = await setup(tmp_path)
        (root/'index.html').write_text('<html><body>Company</body></html>')
        service=tools.registry.get('workspace_create_file').service
        tools.registry.tools['generate_image']=GenerateImage(Images(),None,service)
        run=await repo.patch('run',run['id'],scope,request={**run['request'],'text':'Generate a company logo and use it in the navigation'})
        class Model:
            calls=0
            async def call(self,context):
                self.calls+=1
                if self.calls==1: return Decision(kind='tool',name='generate_image',arguments={'prompt':'A refined company logo'})
                if self.calls==2: return Decision(kind='final',text='Logo generated and integrated.')
                if self.calls==3:
                    assert any('not rendered in the website' in item for item in context.feedback)
                    return Decision(kind='tool',name='workspace_read_file',arguments={'relative_path':'index.html'})
                if self.calls==4:
                    image=next(r.data['path'] for r in context.results if r.data.get('image'))
                    return Decision(kind='tool',name='workspace_write_file',arguments={'relative_path':'index.html',
                        'content':f'<html><body><nav><img src="{image}" alt="Company logo"/>Company</nav></body></html>',
                        'expected_sha256':context.results[-1].data['sha256']})
                return Decision(kind='final',text='Generated the company logo and added it to navigation.')
        model=Model()
        orchestrator=RunOrchestrator(Planner(),ContextBuilder(),MemoryService(repo),EmptyRag(),model,tools,None,
            ValidationService(),Finalizer(repository,repo),runs,Settings(data_dir=tmp_path,workspace_max_steps=12,workspace_max_batches=1),
            WebsiteWorkflow(service,repo,runs.publisher,model))
        await orchestrator.run(run['id'],scope)
        saved=await runs.get(run['id'],scope)
        assert saved['status']=='completed',saved.get('error')
        image=saved['generated_images'][0]['path']
        assert image.startswith('assets/generated/company-logo-') and (root/image).is_file()
        assert image in (root/'index.html').read_text()
        assert saved['image_integration']['passed']
        events=await runs.activity(run['id'],scope)
        assert any(e['event']=='feedback.retrying' for e in events)
        assert not any(e['event']=='commentary' and e['data']['component']=='feedback' for e in events)
        assert len([e for e in events if e['event']=='final'])==1
    asyncio.run(check())


def test_image_import_without_render_does_not_pass_integration(tmp_path):
    async def check():
        root, _, _, _, scope, run, tools=await setup(tmp_path)
        service=tools.registry.get('workspace_create_file').service
        (root/'src').mkdir();(root/'src/App.jsx').write_text('import logo from "../logo.png"; export default () => <h1>Company</h1>')
        images=[{'path':'logo.png','integration_required':True}]
        assert await integration_feedback(service,scope,run['project_workspace_id'],images)
        (root/'src/App.jsx').write_text('import logo from "../logo.png"; export default () => <img src={logo} alt="Company"/>')
        assert await integration_feedback(service,scope,run['project_workspace_id'],images)==''
    asyncio.run(check())


def test_parallel_agent_lifecycle_ids_and_cancellation(tmp_path):
    async def check():
        _,repo,_,runs,scope,run,_=await setup(tmp_path)
        release=asyncio.Event()
        class Agent:
            async def run(self,model,run,feedback):
                await release.wait()
                return SubAgentResult(feedback='Reviewed')
        manager=SubAgentManager(SimpleNamespace(get=lambda name:Agent()),repo,None,runs.publisher)
        tasks=[asyncio.create_task(manager.run_agent('reviewer',scope,run,'Review')) for _ in range(2)]
        for _ in range(100):
            events=await runs.activity(run['id'],scope)
            if len([e for e in events if e['event']=='agent.started'])==2: break
            await asyncio.sleep(.01)
        starts=[e for e in events if e['event']=='agent.started']
        assert len({e['data']['details']['agent_id'] for e in starts})==2
        tasks[0].cancel();release.set()
        await asyncio.gather(*tasks,return_exceptions=True)
        events=await runs.activity(run['id'],scope)
        assert any(e['event']=='agent.cancelled' for e in events)
        assert any(e['event']=='agent.completed' for e in events)
    asyncio.run(check())


def test_workspace_image_preview_is_authenticated_and_root_scoped(tmp_path):
    import httpx
    from app.core.container import AppContainer
    from app.main import create_app
    from app.schemas.contracts import Scope
    async def check():
        container=AppContainer(Settings(data_dir=tmp_path/'data',tokens={'alice':['alice','workspace'],'bob':['bob','workspace']}))
        root=tmp_path/'site';root.mkdir();(root/'logo.png').write_bytes(b'image pixels')
        outside=tmp_path/'outside.png';outside.write_bytes(b'private');(root/'escape.png').symlink_to(outside)
        workspace=await container.workspaces.create(Scope(user_id='alice',workspace_id='workspace'),str(root))
        url=f"/api/workspaces/{workspace['id']}/image"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(container)),base_url='http://test') as client:
            assert (await client.get(url,params={'path':'logo.png'})).status_code==401
            assert (await client.get(url,params={'path':'logo.png'},headers={'Authorization':'Bearer bob'})).status_code==404
            response=await client.get(url,params={'path':'logo.png'},headers={'Authorization':'Bearer alice'})
            assert response.status_code==200 and response.content==b'image pixels'
            assert response.headers['content-type']=='image/png'
            assert (await client.get(url,params={'path':'escape.png'},headers={'Authorization':'Bearer alice'})).status_code==422
    asyncio.run(check())


def test_image_in_unused_component_is_not_website_integration(tmp_path):
    async def check():
        root,_,_,_,scope,run,tools=await setup(tmp_path)
        service=tools.registry.get('workspace_create_file').service
        (root/'src').mkdir()
        (root/'src/main.jsx').write_text('import App from "./App"; createRoot(root).render(<App/>);')
        (root/'src/App.jsx').write_text('import Navbar from "./Navbar"; export default () => <h1>Company</h1>')
        (root/'src/Navbar.jsx').write_text('import logo from "../logo.png"; export default () => <img src={logo}/>')
        images=[{'path':'logo.png','integration_required':True}]
        assert await integration_feedback(service,scope,run['project_workspace_id'],images)
        (root/'src/App.jsx').write_text('import Navbar from "./Navbar"; export default () => <Navbar/>')
        assert await integration_feedback(service,scope,run['project_workspace_id'],images)==''
    asyncio.run(check())


def test_image_retry_with_an_automatic_or_new_path_resolves_failure():
    from app.workspaces.feedback_loop import WorkspaceFeedbackLoop
    from app.schemas.contracts import ToolResult
    loop=WorkspaceFeedbackLoop()
    loop.failed('generate_image',{'prompt':'Company logo'},ToolResult(status='error',error='Temporary provider failure'))
    loop.accepted('generate_image',{'prompt':'Company logo'},ToolResult(status='success',data={'path':'assets/generated/logo.png'}))
    assert loop.final_feedback()==''
