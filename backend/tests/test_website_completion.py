import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.harness.context_builder import ContextBuilder
from app.harness.execution_events import envelope, sanitize
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
from app.tools.workspace_tools import CreateFile, PatchFile
from app.validation.validation_service import ValidationService
from app.workspaces.completion_contract import WebsiteCompletionContract, project_plan
from app.workspaces.provider import LocalWorkspaceProvider
from app.workspaces.service import WorkspaceService
from app.workspaces.website_workflow import WebsiteWorkflow


def test_events_preserve_metrics_and_redact_secrets():
    data = sanitize({'input_tokens': 23, 'output_token_count': 42, 'api_key': 'secret',
                     'arguments': {'path': '.env', 'content': 'password=hunter2'},
                     'stderr': 'mongodb://alice:hunter2@host/db Bearer abc.def token=hidden'})
    assert data['input_tokens'] == 23 and data['output_token_count'] == 42
    assert 'hunter2' not in json.dumps(data) and 'abc.def' not in json.dumps(data)
    event = envelope('tool.completed', {'summary': 'Created Hero', 'duration_ms': 18},
                     {'id': 'run', 'thread_id': 'thread', 'workspace_id': 'workspace'})
    assert event['run_id'] == 'run' and event['conversation_id'] == 'thread'
    assert event['status'] == 'success' and event['duration_ms'] == 18


def test_small_file_output_is_rejected_against_plan():
    async def check():
        files = {'src/App.jsx': 'export default () => <h1>hero service contact</h1>', 'package.json': '{}', 'index.html': '<div id="root"></div>'}
        async def read(path): return files.get(path, '')
        contract = WebsiteCompletionContract()
        await contract.inspect(read, project_plan([]))
        assert not contract.passed
        assert any('Navbar' in error for error in contract.errors)
        assert not contract.checks['app_wired']
    asyncio.run(check())


def test_existing_typescript_conventions_are_preserved():
    plan = project_plan(['src/main.tsx', 'src/App.tsx', 'vite.config.mts', 'src/index.css', 'src/ui/Header.tsx', 'src/ui/Work.tsx'])
    assert plan['expected_components']['Navbar'] == 'src/ui/Header.tsx'
    assert plan['expected_components']['Portfolio'] == 'src/ui/Work.tsx'
    assert 'vite.config.mts' in plan['expected_files'] and 'src/index.css' in plan['expected_files']


class EmptyRag:
    async def retrieve(self, *args): return RagContext()


class WebsiteModel:
    def __init__(self, files, incomplete=False):
        self.files, self.incomplete, self.visual_reviews = list(files.items()), incomplete, 0

    async def call(self, context):
        if self.files:
            path, content = self.files.pop(0)
            return Decision(kind='tool', name='workspace_create_file', arguments={'relative_path': path, 'content': content})
        return Decision(kind='final', text='Your React + Vite business portfolio is complete.')

    async def visual_review(self, screenshots, brief):
        self.visual_reviews += 1
        assert len(screenshots) == 2 and all(Path(path).stat().st_size > 1000 for path in screenshots)
        assert brief['section_specs'] and brief['color_strategy']
        return passing_review()


def passing_review():
    from app.workspaces.visual_quality import RUBRIC
    return {'passed': True, 'desktop': {'passed': True, 'scores': dict.fromkeys(RUBRIC, 4), 'issues': []},
            'mobile': {'passed': True, 'scores': dict.fromkeys(RUBRIC, 4), 'issues': []}}


def website_files():
    plan = project_plan([])
    files = {'package.json': json.dumps({'type': 'module', 'scripts': {'build': 'vite build'},
                  'dependencies': {'react': '*', 'react-dom': '*', 'vite': '*'}}),
             'index.html': '<html lang="en"><head><meta name="viewport" content="width=device-width, initial-scale=1"/><title>Meridian Studio</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>',
             'vite.config.ts': 'import { defineConfig } from "vite"; export default defineConfig({});',
             'src/main.jsx': 'import React from "react"; import {createRoot} from "react-dom/client"; import App from "./App"; createRoot(document.getElementById("root")).render(<App/>);',
             'README.md': '# Meridian Studio\nBusiness portfolio. npm install; npm run build.'}
    imports = []
    for name, path in plan['expected_ui'].items():
        files[path] = f'import React from "react"; export default function {name}({{children}}){{return <div>{{children}}</div>}}'
        imports.append(f'import {name} from "./{path[4:]}";')
    for i, path in enumerate([plan['expected_assets']['hero'], *plan['expected_assets']['portfolio']]):
        files[path] = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500"><rect width="800" height="500" fill="#{["c1d4bf", "dcbe89", "b1c0dc", "dfada2"][i]}"/><circle cx="400" cy="250" r="180" fill="#253b39"/><rect x="200" y="150" width="400" height="200" rx="20" fill="#f4f1ea"/><path d="M260 290L330 190L400 290Z" fill="#576f60"/><text x="450" y="250" font-size="32" fill="#253b39">MERIDIAN</text></svg>'
    for name, path in plan['expected_components'].items():
        imports.append(f'import {name} from "./{path[4:]}";')
        asset_imports = ''
        if name == 'Navbar': markup = '<nav><a href="#hero">Meridian Studio</a><a href="#services">Services</a><a href="#portfolio">Work</a><a href="#about">About</a><a href="#contact">Contact</a></nav>'
        elif name == 'Hero':
            asset_imports = 'import hero from "../assets/hero-art.svg";'
            markup = '<section id="hero"><p>Independent digital studio</p><h1>Ideas built for tomorrow</h1><p>Strategic design for ambitious businesses.</p><a href="#portfolio">View selected work</a><a href="#contact">Start a project</a><img src={hero} alt="Meridian architectural brand composition"/></section>'
        elif name == 'Portfolio':
            asset_imports = ''.join(f'import project{i} from "../assets/project-{i}.svg";' for i in range(1,4))
            markup = '<section id="portfolio"><h2>Selected work</h2>' + ''.join(f'<article data-project><img src={{project{i}}} alt="Atlas brand case study {i}"/><p>Digital product · 2026</p><h3>Atlas Brand Transformation {i}</h3><p>A sustainable commerce experience redesigned around clarity and conversion. +42% checkout completion.</p><a href="#contact">View case study</a></article>' for i in range(1,4)) + '</section>'
        elif name == 'Testimonials': markup = '<section id="testimonials"><h2>Trusted collaborators</h2><blockquote>Meridian brought clarity and distinction to our launch.</blockquote><cite>Alex Chen · Founder, Atlas</cite></section>'
        elif name == 'ContactCTA': markup = '<section id="contact"><h2>Have a project in mind?</h2><p>Let us build something worth remembering.</p><a href="mailto:hello@example.com">Start a project</a><a href="#portfolio">View our work</a></section>'
        elif name == 'Footer': markup = '<footer><h2>Meridian Studio</h2><p>Independent design partners for ambitious brands. New York and everywhere. Copyright 2026.</p><a href="#services">Services</a><a href="#portfolio">Work</a><a href="#about">About</a><a href="mailto:hello@example.com">Contact</a><a href="https://example.com">Social</a></footer>'
        else: markup = f'<section id="{name.lower()}"><h2>{name}</h2><p>01 · Clarity and craft for businesses moving forward.</p></section>'
        files[path] = f'import React from "react"; {asset_imports} export default function {name}() {{return ({markup});}}'
    for name in ('portfolio', 'services', 'testimonials'):
        files[f'src/data/{name}.js'] = 'export default [{name: "Atlas Brand Transformation"}];'
        imports.append(f'import {name} from "./data/{name}";')
    for path in ('src/styles/globals.css', 'src/styles/tokens.css', 'src/styles/animations.css', 'src/styles/layout.css'): imports.append(f'import "./{path[4:]}";')
    files['src/styles/globals.css'] = 'body{margin:0;font:16px Arial;background:#f4f1ea;color:#20252a}nav,footer{padding:24px}nav{display:flex;flex-wrap:wrap;gap:12px}section{padding:48px 6%;background:#f4f1ea}section:nth-child(even){background:#dbe4db}h1{font-size:64px;max-width:900px}a{display:inline-flex;align-items:center;padding:12px;color:inherit}a:focus-visible{outline:3px solid #20252a}img{width:100%;max-width:800px;height:auto} @media(max-width:500px){h1{font-size:40px}section{padding:28px 6%}}'
    files['src/styles/tokens.css'] = ':root{--accent:#495a44;--space-section:96px}'
    files['src/styles/layout.css'] = 'main{max-width:1440px;margin:auto}article{max-width:800px}'
    files['src/styles/animations.css'] = 'a,img{transition:transform .2s}a:hover{transform:translateY(-2px)}img:hover{transform:scale(1.01)}section{animation:reveal .3s ease-out}@keyframes reveal{from{opacity:.5;transform:translateY(8px)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}'
    files['src/App.jsx'] = 'import React from "react";\n' + '\n'.join(imports) + '\nexport default function App(){return <><Navbar/><main>' + ''.join(f'<{name}/>' for name in plan['expected_components'] if name not in {'Navbar', 'Footer'}) + '<Button/><SectionHeading/><ProjectCard/><ServiceCard/><p>{portfolio[0].name} · {services[0].name} · {testimonials[0].name}</p></main><Footer/></>}'
    return files


async def harness(tmp_path, files, browser=False, model_factory=WebsiteModel, max_steps=80):
    root = tmp_path / 'website'; root.mkdir()
    if browser:
        # Reuse installed test dependencies; the build and browser run against real files.
        dependencies = Path(__file__).parents[2] / 'frontend/node_modules'
        if not dependencies.exists(): raise AssertionError('Install frontend dependencies before this integration test')
        (root / 'node_modules').symlink_to(dependencies, target_is_directory=True)
    db = Database(tmp_path / 'runs.db'); repo = EntityRepository(db)
    repository = RunRepository(db, repo); runs = RunService(repository, repo)
    scope = Scope(user_id='test', workspace_id='test')
    workspace = WorkspaceService(repo, LocalWorkspaceProvider())
    selected = await workspace.create(scope, str(root))
    thread = await repo.create('thread', scope, '', title='Website test')
    request = MessageRequest(thread_id=thread['id'], text='Build aesthetic business website portfolio. Use React + Vite.', idempotency_key='site')
    run = await repository.submit(scope, request)
    run = await repo.patch('run', run['id'], scope, mode='workspace', project_workspace_id=selected['id'])
    model = model_factory(files)
    workflow = WebsiteWorkflow(workspace, repo, runs.publisher, model)
    orchestrator = RunOrchestrator(Planner(), ContextBuilder(), MemoryService(repo), EmptyRag(), model,
        ToolOrchestrator(ToolRegistry([CreateFile(workspace), PatchFile(workspace)]), repo, runs, workspace_max_calls=80),
        None, ValidationService(), Finalizer(repository, repo), runs, Settings(data_dir=tmp_path, workspace_max_steps=max_steps, workspace_max_batches=1), workflow)
    await orchestrator.run(run['id'], scope)
    return await runs.get(run['id'], scope), await runs.activity(run['id'], scope), model, repo, scope


def test_incomplete_website_keeps_repairing_until_run_budget(tmp_path):
    async def check():
        run, events, model, repo, scope = await harness(tmp_path, {'src/App.jsx': 'export default () => <h1>Hero service contact</h1>'}, max_steps=12)
        assert run['status'] == 'failed'
        assert len([event for event in events if event['event'] == 'feedback.retrying']) == 11
        assert not any(event['event'] == 'final' for event in events)
        assert not run['website_validation']['passed']
        assert model.visual_reviews == 0
    asyncio.run(check())


def test_complete_portfolio_build_preview_screenshots_and_finalization(tmp_path):
    async def check():
        run, events, model, repo, scope = await harness(tmp_path, website_files(), browser=True)
        assert run['status'] == 'completed', run.get('error')
        assert run['website_validation']['passed']
        assert run['website_validation']['checks']['screenshot_review']
        assert len(run['website_preview']['viewports']) == 2 and model.visual_reviews == 1
        plan = run['implementation_plan']
        assert len(plan['expected_components']) == 9 and 'run_visual_qa' in plan['steps']
        commentary = [event for event in events if event['event'] == 'commentary']
        assert commentary and commentary[0]['data']['details']['text'].startswith('I’ll inspect')
        event_types = [event['event'] for event in events]
        assert event_types.index('validation.success') < event_types.index('final')
        tool_events = [event for event in events if event['event'] == 'tool']
        assert len(tool_events) == len(website_files())
        assert all(event['data']['details']['tool_call_id'] for event in tool_events)
        changes = await repo.list('workspace_change', scope)
        assert all(change.get('tool_run_id') and change.get('after_sha256') for change in changes)
    asyncio.run(check())


class RepairWebsiteModel(WebsiteModel):
    def __init__(self, files):
        super().__init__(files)
        self.deferred = self.files.pop(next(i for i, (path, _) in enumerate(self.files) if path == 'src/styles/animations.css'))
        self.attempted_final = False

    async def call(self, context):
        if self.files: return await super().call(context)
        if not self.attempted_final:
            self.attempted_final = True
            return Decision(kind='final', text='Website complete.')
        if self.deferred:
            assert any('animations.css' in message for message in context.feedback)
            path, content = self.deferred; self.deferred = None
            return Decision(kind='tool', name='workspace_create_file', arguments={'relative_path': path, 'content': content})
        return await super().call(context)


def test_missing_planned_file_is_repaired_before_delivery(tmp_path):
    async def check():
        run, events, model, _, _ = await harness(tmp_path, website_files(), browser=True, model_factory=RepairWebsiteModel)
        assert run['status'] == 'completed', run.get('error')
        assert run['attempts'] == 1
        types = [event['event'] for event in events]
        assert types.index('feedback.retrying') < types.index('final')
        assert model.visual_reviews == 1
    asyncio.run(check())


def test_importing_unused_components_cannot_satisfy_contract():
    async def check():
        files = website_files()
        files['src/App.jsx'] = files['src/App.jsx'].replace('<Hero/>', '')
        async def read(path): return files.get(path, '')
        contract = WebsiteCompletionContract()
        await contract.inspect(read, project_plan([]))
        assert not contract.checks['wired:Hero']
    asyncio.run(check())


def test_readonly_react_questions_do_not_trigger_generation():
    assert WebsiteWorkflow.classify('Explain this React website')['requires_full_project'] is False
    assert WebsiteWorkflow.classify('Build a React + Vite app')['requires_full_project'] is True


def failing_review():
    review = passing_review()
    review['passed'] = False
    review['desktop']['issues'] = [{'severity': 'high', 'section': 'hero',
        'problem': 'The dark rectangle is empty and project cards are text-only.',
        'fix': 'Render the original hero artwork and visual case-study cards with varied surfaces.'}]
    return review


def test_screenshot_rubric_rejects_high_issues_missing_views_and_weak_scores():
    from app.workspaces.visual_quality import evaluate_review
    review = failing_review(); review['passed'] = True
    assert evaluate_review(review)['passed'] is False
    assert evaluate_review(review)['high_severity_visual_issues'] == 1
    assert evaluate_review({'passed': True})['passed'] is False
    review = passing_review(); review['mobile']['scores']['typography'] = 2
    assert evaluate_review(review)['passed'] is False
    assert evaluate_review(passing_review())['passed'] is True


class VisualRepairModel(WebsiteModel):
    def __init__(self, files):
        super().__init__(files)
        good = website_files()
        self.repairs = [(path, files[path], good[path]) for path in files if files[path] != good[path]]

    async def visual_review(self, screenshots, brief):
        await super().visual_review(screenshots, brief)
        return failing_review() if self.visual_reviews == 1 else passing_review()

    async def call(self, context):
        if self.files: return await super().call(context)
        if self.visual_reviews and self.repairs:
            assert len(context.request['repair_screenshots']) == 2
            assert any('workspace_diff' in item and 'build_result' in item and 'original_request' in item for item in context.feedback)
            path, before, after = self.repairs.pop(0)
            return Decision(kind='tool', name='workspace_patch_file', arguments={'relative_path': path, 'find': before, 'replace': after})
        return await super().call(context)


def test_weak_rendered_portfolio_is_targeted_repaired_and_rebuilt(tmp_path):
    async def check():
        files = website_files()
        hero = 'src/components/Hero.jsx'
        files[hero] = files[hero].replace('<img src={hero} alt="Meridian architectural brand composition"/>', '<div className="hero-visual" style={{height:300,background:"#152421"}}/>')
        portfolio = 'src/components/Portfolio.jsx'
        import re
        files[portfolio] = re.sub(r'<img src=\{project[123]\}[^>]+/>', '', files[portfolio])
        files['src/components/Services.jsx'] = files['src/components/Services.jsx'].replace('01 ·', '🎨')
        files['src/styles/globals.css'] = files['src/styles/globals.css'].replace('background:#dbe4db', 'background:#f4f1ea')
        files['src/components/Footer.jsx'] = 'import React from "react";export default function Footer(){return <footer>Meridian Studio</footer>}'
        run, events, model, _, _ = await harness(tmp_path, files, browser=True, model_factory=VisualRepairModel)
        assert run['status'] == 'completed', run.get('error')
        assert model.visual_reviews == 2 and run['visual_repair_attempts'] == 1
        assert all(value is True for key, value in run['website_validation']['completion_contract'].items() if key != 'high_severity_visual_issues')
        assert run['website_validation']['completion_contract']['high_severity_visual_issues'] == 0
        failures = [e['data']['details'] for e in events if e['event'] == 'visual_qa.failed' and 'evidence' in e['data']['details']]
        checks = failures[0]['evidence']['viewports'][0]['checks']
        assert not checks['meaningful_hero_visual'] and not checks['portfolio_visuals']
        assert not checks['tonal_hierarchy'] and not checks['refined_service_icons'] and not checks['developed_footer']
        types = [e['event'] for e in events]
        assert types.index('design.started') < types.index('code.started') < types.index('repair.started') < types.index('final')
        assert run['repair_context']['screenshots'] and run['repair_context']['workspace_diff']
        assert len([e for e in events if e['event'] == 'terminal.success' and e['data']['details'].get('command') == 'npm run build']) == 2
    asyncio.run(check())


class UnpolishedModel(WebsiteModel):
    async def visual_review(self, screenshots, brief):
        await super().visual_review(screenshots, brief)
        return failing_review()


def test_visual_repairs_stop_at_three_without_false_success(tmp_path):
    async def check():
        run, events, model, _, _ = await harness(tmp_path, website_files(), browser=True, model_factory=UnpolishedModel)
        assert run['status'] == 'failed'
        assert '3 visual repair attempts' in run['error']
        assert run['visual_repair_attempts'] == 3 and model.visual_reviews == 4
        assert not run['website_validation']['passed']
        assert not any(e['event'] == 'final' for e in events)
    asyncio.run(check())


def test_generated_images_can_replace_planned_svg_fallbacks():
    async def check():
        files = website_files()
        path = 'src/assets/hero-art.svg'
        files['src/assets/hero-art.png'] = '[binary asset]'
        files.pop(path)
        files['src/components/Hero.jsx'] = files['src/components/Hero.jsx'].replace('hero-art.svg', 'hero-art.png')
        async def read(path): return files.get(path, '')
        contract = WebsiteCompletionContract()
        await contract.inspect(read, project_plan([]))
        assert contract.passed, contract.errors
        files['src/App.jsx'] = files['src/App.jsx'].replace('<Button/>', '')
        contract = WebsiteCompletionContract()
        await contract.inspect(read, project_plan([]))
        assert not contract.checks['wired:Button']
    asyncio.run(check())


def test_real_mobile_menu_opens_and_closes_before_capture(tmp_path):
    async def check():
        files = website_files()
        files['src/components/Navbar.jsx'] = 'import React from "react";export default function Navbar(){const [open,setOpen]=React.useState(false);return <nav><a href="#hero">Meridian Studio</a><button className="menu-button" aria-expanded={open} aria-controls="nav-links" onClick={()=>setOpen(!open)}>Menu</button><div id="nav-links" className={open ? "menu-links open" : "menu-links"}><a href="#services">Services</a><a href="#portfolio">Work</a><a href="#about">About</a><a href="#contact">Contact</a></div></nav>}'
        files['src/styles/layout.css'] += '.menu-button{display:none}.menu-links{display:flex}@media(max-width:500px){.menu-button{display:inline-flex;padding:12px}.menu-links{display:none}.menu-links.open{display:flex;flex-direction:column}}'
        run, _, _, _, _ = await harness(tmp_path, files, browser=True)
        assert run['status'] == 'completed', run.get('error')
        mobile = next(view for view in run['website_preview']['viewports'] if view['name'] == 'mobile')
        assert mobile['checks']['mobile_menu']
        assert mobile['checks']['reduced_motion_behavior']
        assert mobile['checks']['keyboard_focus'] and mobile['checks']['hover_interaction']
    asyncio.run(check())
