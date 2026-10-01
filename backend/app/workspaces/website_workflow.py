import asyncio
import json
import os
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from app.workspaces.completion_contract import WebsiteCompletionContract, project_plan
from app.workspaces.design_agent import DesignAgent
from app.workspaces.visual_quality import evaluate_review


class WebsiteWorkflow:
    """Inspect, plan, execute validation, and require evidence before delivery."""
    def __init__(self, workspaces, repo, publisher=None, model=None):
        self.workspaces, self.repo, self.publisher, self.model = workspaces, repo, publisher, model

    @staticmethod
    def classify(text):
        words = text.lower()
        website = any(term in words for term in ('website', 'web site', 'landing page', 'portfolio', 'react', 'vite', 'frontend', 'web page', 'dashboard', 'user interface'))
        build = any(term in words for term in ('build', 'create', 'generate', 'develop', 'implement', 'make', 'design', 'redesign', 'refine', 'polish', 'restyle', 'improve', 'edit'))
        website = website and build
        react = 'react' in words or 'vite' in words
        return {'task_type': 'website_generation' if website else 'workspace_task', 'project_type': 'react_vite' if react else 'website',
                'quality_target': 'production_polished', 'requires_full_project': website, 'requires_build': website,
                'requires_preview': website, 'requires_visual_validation': website, 'visual_quality_required': website,
                'browser_validation_required': website, 'build_validation_required': website,
                'responsive_validation_required': website, 'requires_design_agent': website}

    async def emit(self, run, component, summary, status='success', **details):
        if self.publisher:
            await self.publisher.emit(run_id=run['id'], component=component, component_name=details.pop('component_name', component),
                                      event_type=f'{component}.{status}', status=status, summary=summary, details=details)

    async def prepare(self, scope, run):
        classification = self.classify(run['request']['text'])
        workspace_id = run['project_workspace_id']
        context = await self.workspaces.context(scope, workspace_id)
        package = await self._read(scope, workspace_id, 'package.json')
        react = classification['project_type'] == 'react_vite' or 'react' in package
        if classification['requires_full_project'] and react: classification['project_type'] = 'react_vite'
        inspection = {**context, 'project_root': '.', 'project_state': 'existing' if context['files'] else 'empty',
                      'package_manager': 'npm', 'build_command': 'npm run build', 'build_tool': 'Vite' if react else 'static'}
        await self.emit(run, 'workspace', 'Inspected selected project root', **inspection)
        if not classification['requires_full_project']:
            words = run['request']['text'].lower()
            visual_edit = (react or 'index.html' in context['files']) and any(word in words for word in ('style', 'color', 'typography', 'spacing', 'animation', 'button', 'layout', 'hero', 'navbar')) and any(word in words for word in ('change', 'edit', 'add', 'fix', 'improve', 'polish', 'refine', 'update'))
            if visual_edit:
                classification['requires_design_agent'] = True
                await self.emit(run, 'design', 'DesignAgent started for visual refinement', 'started', component_name='DesignAgent')
                brief = DesignAgent().create(run['request']['text'], {'expected_components': {}})
                brief['project_type'] = 'visual_refinement'
                await self.repo.patch('run', run['id'], scope, design_brief=brief)
                await self.emit(run, 'design', 'Design system created for requested changes', component_name='DesignAgent', design_brief=brief)
            await self.repo.patch('run', run['id'], scope, task_classification=classification, workspace_inspection=inspection)
            return classification, 'Workspace inspection: ' + json.dumps(inspection) + ('\nImplement only the requested visual refinement; use relevant specifications from this DesignBrief without scaffolding unrelated sections: ' + json.dumps(brief) if visual_edit else '')
        plan = run.get('implementation_plan') or project_plan(context['files'], react)
        await self.emit(run, 'design', 'DesignAgent started', 'started', component_name='DesignAgent')
        previous_brief = run.get('design_brief') or {}
        brief = previous_brief if previous_brief.get('version') == 2 else DesignAgent().create(run['request']['text'], plan)
        if getattr(self, 'image_generation_available', False):
            brief['image_strategy']['workspace_asset_mode'] = 'generate_image_with_local_svg_fallback'
            brief['image_strategy']['generation_instruction'] = 'Use generate_image with relative_path in src/assets for meaningful project-safe PNG/JPEG imagery. Use the planned hero and project asset stems with PNG/JPEG extensions; these satisfy the asset contract in place of SVG fallbacks. Import and render the returned asset. Keep deliberate SVG fallback artwork if generation fails; never use broken external URLs.'
        await self.repo.patch('run', run['id'], scope, task_classification=classification, workspace_inspection=inspection,
                              implementation_plan=plan, design_brief=brief)
        await self.emit(run, 'planner', 'Created complete website implementation plan', **plan)
        await self.emit(run, 'planner', 'Created website design system', component_name='DesignAgent', design_brief=brief)
        await self.emit(run, 'design', 'Section specifications and asset strategy created', component_name='DesignAgent', sections=brief['section_specs'], assets=brief['asset_strategy'])
        return classification, ('Completion contract: create the complete planned project in the selected root, preserve existing conventions, '
                'and use as many file operations as needed. Never create a nested duplicate. A final answer is rejected until planned '
                'files exist and are imported, build passes, desktop/mobile previews and screenshots pass, and visual QA passes. '
                'Use workspace tools to implement this design and plan.\nImplementation plan: ' + json.dumps(plan) + '\nDesign brief: ' + json.dumps(brief) + '\nInspection: ' + json.dumps(inspection))

    async def validate(self, scope, run):
        current = await self.repo.get('run', run['id'], scope)
        workspace_id = run['project_workspace_id']
        react = current['task_classification']['project_type'] == 'react_vite'
        contract = WebsiteCompletionContract()
        plan = current['implementation_plan']
        evidence, visual_review = None, None
        await self.emit(run, 'validation', 'Checking planned files, manifest, entrypoint and imports', 'started', target='.', validator='WebsiteBuildValidator')
        await contract.inspect(lambda path: self._read(scope, workspace_id, path), plan, react)
        async def finish():
            report = contract.report()
            checks = contract.checks
            report['technical_passed'] = all(value for key, value in checks.items() if key.startswith(('file:', 'wired:', 'import:')) or key in {'manifest', 'build_script', 'html_entrypoint', 'app_wired', 'build_passed', 'dist_index', 'dist_assets', 'preview_loaded', 'browser_errors'})
            report['visual_passed'] = checks.get('visual_validation', False) and checks.get('screenshot_review', False)
            report['visual_failure'] = evidence is not None and report['technical_passed'] and not report['visual_passed']
            report['visual_qa'] = visual_review
            report['completion_contract'] = {
                'project_structure_complete': all(value for key, value in checks.items() if key.startswith('file:')),
                'planned_sections_complete': all(checks.get('wired:' + name, not react) for name in plan.get('expected_sections', [])) and checks.get('planned_sections_rendered', False),
                'build_passed': checks.get('build_passed', False), 'preview_loaded': checks.get('preview_loaded', False),
                'runtime_validation_passed': checks.get('browser_errors', False),
                'desktop_validation_passed': checks.get('desktop_validation', False), 'mobile_validation_passed': checks.get('mobile_validation', False),
                'visual_quality_passed': report['visual_passed'], 'high_severity_visual_issues': (visual_review or {}).get('high_severity_visual_issues', 0)}
            if report['passed'] and not all(value is True for key, value in report['completion_contract'].items() if key != 'high_severity_visual_issues'):
                report.update(passed=False, retryable=True, feedback='Final completion contract is incomplete.')
            await self.repo.patch('run', run['id'], scope, website_validation=report)
            await self.emit(run, 'validation', 'Website completion contract passed' if report['passed'] else 'Website completion contract failed',
                            'success' if report['passed'] else 'failed', **report)
            return report['passed'], report['feedback']
        if not contract.passed: return await finish()
        workspace = await self.workspaces.get(scope, workspace_id)
        root = self.workspaces.provider.root(workspace['root_id'])
        if react:
            if not (root / 'node_modules' / '.bin' / 'vite').exists():
                install = await self._command(scope, run, 'npm install')
                contract.check('dependencies_installed', install['exit_code'] == 0, 'Dependency installation failed: ' + install['stderr'][-1500:])
                if not contract.passed: return await finish()
            build = await self._command(scope, run, 'npm run build')
            contract.check('build_passed', build['exit_code'] == 0, 'Build failed: ' + (build['stderr'] or build['stdout'])[-2000:])
            contract.check('dist_index', bool(await self._read(scope, workspace_id, 'dist/index.html')), 'Build must produce dist/index.html.')
            dist = root / 'dist'
            contract.check('dist_assets', (dist / 'assets').is_dir() and any((dist / 'assets').iterdir()), 'Build must produce bundled assets.')
        else:
            build = {'exit_code': 0, 'stdout': 'Static website; no compilation required.', 'stderr': ''}
            contract.check('build_passed', True, '')
            contract.check('dist_assets', True, '')
            dist = root
        await self.repo.patch('run', run['id'], scope, website_build_result=build)
        if not contract.passed: return await finish()
        try:
            await self.emit(run, 'preview', 'Starting controlled preview and inspecting desktop/mobile pages', 'started', widths=[1440, 390])
            evidence = await asyncio.to_thread(self._capture, dist, root / '.harness-preview', run['id'], current['design_brief'], plan.get('expected_sections', list(plan.get('expected_components', {}))))
            contract.check('viewport_evidence', {v['name'] for v in evidence['viewports']} == {'desktop', 'mobile'} and len(evidence['viewports']) == 2, 'Capture both desktop and mobile screenshots.')
            await self.repo.patch('run', run['id'], scope, website_preview=evidence)
            for viewport in evidence['viewports']:
                await self.emit(run, 'preview', 'Captured ' + viewport['name'] + ' screenshot', screenshot=viewport['screenshot'], width=viewport['width'], checks=viewport['checks'])
            contract.check('preview_loaded', evidence['loaded'], 'Preview is blank or failed to load.')
            contract.check('browser_errors', not evidence['errors'], 'Browser/resource errors: ' + '; '.join(evidence['errors'][:5]))
            contract.check('responsive_validation', all(v['checks']['no_overflow'] for v in evidence['viewports']), 'Repair horizontal overflow on desktop or mobile.')
            contract.check('planned_sections_rendered', all(v['checks'].get('planned_sections_rendered', False) for v in evidence['viewports']), 'Every planned section must be visibly rendered, not merely imported.')
            for viewport in evidence['viewports']:
                contract.check(viewport['name'] + '_validation', all(viewport['checks'].values()), viewport['name'] + ' browser visual checks failed: ' + ', '.join(key for key, value in viewport['checks'].items() if not value))
            contract.check('visual_validation', all(all(v['checks'].values()) for v in evidence['viewports']), 'Repair visual composition and interactions using the browser evidence.')
            await self.emit(run, 'visual_qa', 'Inspected meaningful hero imagery, visual project cards, surfaces, typography and interactions',
                            'success' if contract.passed else 'failed', component_name='VisualQAAgent', evidence=evidence)
            if self.model is None or not hasattr(self.model, 'visual_review'):
                contract.check('screenshot_review', False, 'Screenshot visual reviewer is unavailable; visual completion cannot be verified.')
            else:
                await self.emit(run, 'model', 'VisualQAAgent reviewing desktop and mobile screenshots', 'started', component_name='VisualQAAgent', provider='Gemini', model=getattr(self.model, 'model', type(self.model).__name__), purpose='visual QA', request_type='multimodal')
                from time import monotonic
                review_started = monotonic()
                review = await self.model.visual_review([v['screenshot'] for v in evidence['viewports']], {**current['design_brief'], 'browser_evidence': evidence})
                visual_review = evaluate_review(review)
                contract.check('screenshot_review', visual_review['passed'], 'Screenshot visual QA: ' + visual_review['feedback'])
                await self.emit(run, 'visual_qa', f"Visual QA found {len(visual_review['issues'])} issues" if not visual_review['passed'] else 'Visual QA passed',
                    'success' if visual_review['passed'] else 'failed', component_name='VisualQAAgent', duration_ms=int((monotonic()-review_started)*1000), review=visual_review, **review.get('metadata', {}))
            await self.repo.patch('run', run['id'], scope, website_preview=evidence)
        except Exception as exc:
            contract.check('preview_validation', False, 'Preview/visual QA failed: ' + str(exc)[:1000])
        return await finish()

    async def prepare_repair(self, scope, run, feedback):
        from app.harness.execution_events import sanitize
        current = await self.repo.get('run', run['id'], scope)
        await self.emit(run, 'repair', 'RepairAgent started', 'started', component_name='RepairAgent')
        inspection = await self.workspaces.inspect(scope, run['project_workspace_id'])
        changes = await self.workspaces.changes(scope, run['project_workspace_id'], run['id'])
        bounded_changes = []
        remaining = 30000
        for change in changes[-30:]:
            diff = change.get('diff', '')[:remaining]
            remaining -= len(diff)
            bounded_changes.append({**change, 'diff': diff})
        packet = sanitize({'original_request': run['request']['text'], 'design_brief': current['design_brief'],
            'screenshots': [v['screenshot'] for v in current.get('website_preview', {}).get('viewports', [])],
            'visual_qa': current.get('website_validation', {}).get('visual_qa'), 'failed_checks': feedback,
            'current_files': inspection['files'], 'workspace_diff': bounded_changes,
            'build_result': current.get('website_build_result', {})})
        # Workspace diffs are always available, including in projects without Git.
        workspace = await self.workspaces.get(scope, run['project_workspace_id'])
        if (self.workspaces.provider.root(workspace['root_id']) / '.git').exists() and workspace['settings'].get('allow_git'):
            import shlex
            paths = []
            for relative in inspection['files']:
                try:
                    self.workspaces.provider.resolve(workspace['root_id'], relative)
                    paths.append(shlex.quote(':(literal)' + relative))
                except ValueError:
                    continue
            if paths:
                git = await self._command(scope, run, 'git diff -- ' + ' '.join(paths))
                packet['git_diff'] = sanitize(git['stdout'][:20000])
        await self.repo.patch('run', run['id'], scope, repair_context=packet)
        await self.emit(run, 'repair', 'Prepared targeted repair evidence', component_name='RepairAgent',
                        files=inspection['files'], screenshots=packet['screenshots'], visual_qa=packet['visual_qa'])
        return packet

    async def _command(self, scope, run, command):
        from time import monotonic
        started = monotonic()
        await self.emit(run, 'terminal', command + ' started', 'started', command=command, target='.')
        try:
            result = await self.workspaces.command(scope, run['project_workspace_id'], command, timeout=60)
        except Exception as exc:
            await self.emit(run, 'terminal', command + ' failed', 'failed', command=command, error=str(exc))
            return {'exit_code': -1, 'stdout': '', 'stderr': str(exc)[:2000]}
        await self.emit(run, 'terminal', command + ' completed', 'success' if result['exit_code'] == 0 else 'failed',
                        command=command, duration_ms=int((monotonic()-started)*1000), **result)
        return result

    async def _read(self, scope, workspace_id, path):
        try: return (await self.workspaces.read(scope, workspace_id, path))['content']
        except (KeyError, ValueError):
            if Path(path).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.woff', '.woff2', '.ico', '.avif'}:
                workspace = await self.workspaces.get(scope, workspace_id)
                resolved = self.workspaces.provider.resolve(workspace['root_id'], path)
                if resolved.is_file(): return '[binary asset]'
            return ''

    @staticmethod
    def _capture(dist, output, run_id, brief=None, expected_sections=None):
        from playwright.sync_api import sync_playwright
        output.mkdir(parents=True, exist_ok=True)
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(dist), **kwargs)
            def log_message(self, _format, *args): pass
            def do_GET(self):
                from urllib.parse import unquote, urlparse
                from app.workspaces.provider import LocalWorkspaceProvider
                target = (dist / unquote(urlparse(self.path).path).lstrip('/')).resolve()
                if not target.is_relative_to(dist.resolve()) or LocalWorkspaceProvider._denied(target.relative_to(dist.resolve())):
                    self.send_error(403); return
                if self.path == '/favicon.ico':
                    self.send_response(204); self.end_headers(); return
                return super().do_GET()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        evidence = {'loaded': True, 'errors': [], 'viewports': []}
        try:
            with sync_playwright() as playwright:
                options = {'headless': True, 'args': ['--no-sandbox']}
                chrome = os.getenv('HARNESS_CHROME_PATH') or shutil.which('google-chrome') or shutil.which('chromium')
                if chrome: options['executable_path'] = chrome
                browser = playwright.chromium.launch(**options)
                for name, width, height in (('desktop', 1440, 1100), ('mobile', 390, 844)):
                    page = browser.new_page(viewport={'width': width, 'height': height})
                    page.on('pageerror', lambda error: evidence['errors'].append(str(error)))
                    page.on('console', lambda message: evidence['errors'].append(message.text) if message.type == 'error' else None)
                    page.on('requestfailed', lambda request: evidence['errors'].append(request.url + ': ' + str(request.failure)))
                    page.on('response', lambda response: evidence['errors'].append(f'{response.status} {response.url}') if response.status >= 400 else None)
                    response = page.goto(f'http://127.0.0.1:{server.server_port}', wait_until='networkidle', timeout=30000)
                    evidence['loaded'] &= bool(response and response.ok and page.locator('body').inner_text().strip())
                    # Reveal content through a real scroll pass before full-page capture.
                    height_total = page.evaluate('document.documentElement.scrollHeight')
                    for y in range(0, height_total, max(300, height // 2)):
                        page.evaluate('(y) => window.scrollTo(0, y)', y)
                        page.wait_for_timeout(40)
                    page.evaluate('window.scrollTo(0, 0)')
                    page.wait_for_timeout(300)
                    quality = page.evaluate(Path(__file__).with_name('browser_quality.js').read_text(),
                        {'allowPlayful': (brief or {}).get('allow_playful_icons', False), 'expectedSections': expected_sections or []})
                    checks = quality['checks']
                    if width < 500:
                        menus = page.locator('nav button[aria-expanded],header button[aria-expanded]')
                        for menu in menus.all():
                            if not menu.is_visible(): continue
                            menu.click()
                            page.wait_for_timeout(200)
                            opened = page.evaluate(Path(__file__).with_name('browser_quality.js').read_text(),
                                {'allowPlayful': (brief or {}).get('allow_playful_icons', False), 'expectedSections': expected_sections or []})
                            checks['mobile_menu'] = menu.get_attribute('aria-expanded') == 'true' and opened['checks']['navigation']
                            checks['navigation'] = opened['checks']['navigation']
                            checks['mobile_targets'] = checks['mobile_targets'] and opened['checks']['mobile_targets']
                            page.screenshot(path=str(output / f'{run_id}-mobile-menu.png'), full_page=True)
                            menu.click()
                            checks['mobile_menu'] &= menu.get_attribute('aria-expanded') == 'false'
                            break
                    # Verify keyboard focus and hover in the actual rendered page.
                    page.keyboard.press('Tab')
                    focus = page.evaluate("() => {const e=document.activeElement,s=getComputedStyle(e);return e!==document.body && (s.outlineStyle!=='none' || s.boxShadow!=='none');}")
                    checks['keyboard_focus'] = focus
                    links = page.locator('nav a, nav button')
                    hover = False
                    for target in links.all():
                        if target.is_visible():
                            target.hover()
                            hover = page.evaluate("() => !!document.querySelector('nav a:hover,nav button:hover')")
                            break
                    checks['hover_interaction'] = hover
                    page.mouse.move(width - 1, height - 1)
                    page.emulate_media(reduced_motion='reduce')
                    reduced = page.evaluate("() => [...document.querySelectorAll('main *,nav a,nav button')].every(e => {const s=getComputedStyle(e);return s.animationDuration.split(',').every(d=>parseFloat(d)<=.01) && s.transitionDuration.split(',').every(d=>parseFloat(d)<=.01)})")
                    checks['reduced_motion_behavior'] = reduced
                    page.emulate_media(reduced_motion='no-preference')
                    evidence.setdefault('interaction_checks', {})[name] = {'keyboard_focus': focus, 'reduced_motion': reduced, 'hover': hover}
                    path = output / f'{run_id}-{name}.png'; page.screenshot(path=str(path), full_page=True)
                    evidence['viewports'].append({'name': name, 'width': width, 'screenshot': str(path), 'checks': checks, 'visual_evidence': quality['evidence']})
                    page.close()
                browser.close()
        finally:
            server.shutdown(); server.server_close()
        return evidence
