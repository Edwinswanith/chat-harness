"""Planned project outputs and evidence required before a website can finish."""
import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

STEPS = ['inspect_workspace', 'detect_project_state', 'create_project_scaffold_if_needed', 'create_design_system',
         'create_layout_components', 'create_content', 'create_styles', 'wire_application', 'install_dependencies_if_needed',
         'run_build', 'repair_build_errors', 'run_preview', 'capture_desktop_screenshot', 'capture_mobile_screenshot',
         'run_visual_qa', 'repair_visual_issues', 'final_validation']
COMPONENTS = {'Navbar': ('nav', 'header'), 'Hero': ('hero',), 'Services': ('service',), 'Portfolio': ('portfolio', 'work', 'project'),
              'About': ('about',), 'Process': ('process',), 'Testimonials': ('testimonial', 'proof'),
              'ContactCTA': ('contact', 'cta'), 'Footer': ('footer',)}
IMPORTS = re.compile(r'''(?:\b(?:import|export)\s+(?:[^;'"\n]*?\s+from\s*)?|\bimport\s*\()\s*['"]([^'"]+)['"]''')


def project_plan(files, react=True):
    def existing(choices): return next((path for path in choices if path in files), choices[0])
    if not react:
        return {'task_type': 'website_generation', 'steps': STEPS, 'expected_files': ['index.html', 'README.md'], 'expected_components': {}, 'expected_sections': list(COMPONENTS), 'entrypoint': 'index.html'}
    ts = any(path.endswith('.tsx') for path in files)
    ext = 'tsx' if ts else 'jsx'
    components = {}
    for name, aliases in COMPONENTS.items():
        candidates = [path for path in files if path.endswith(('.jsx', '.tsx')) and any(alias in PurePosixPath(path).stem.lower() for alias in aliases)]
        components[name] = candidates[0] if candidates else f'src/components/{name}.{ext}'
    main = existing(['src/main.' + ext, 'src/index.' + ext])
    app = existing(['src/App.' + ext, 'src/app.' + ext])
    styles = [existing(['src/styles/globals.css', 'src/index.css', 'src/styles.css']),
              existing(['src/styles/tokens.css']), existing(['src/styles/animations.css'])]
    data = [existing(['src/data/portfolio.ts' if ts else 'src/data/portfolio.js', 'src/data/projects.ts' if ts else 'src/data/projects.js']), existing(['src/data/services.ts' if ts else 'src/data/services.js'])]
    data.append(existing(['src/data/testimonials.ts' if ts else 'src/data/testimonials.js']))
    styles.append(existing(['src/styles/layout.css']))
    ui = {name: existing([f'src/components/ui/{name}.{ext}', f'src/ui/{name}.{ext}']) for name in ('Button', 'SectionHeading', 'ProjectCard', 'ServiceCard')}
    images = [path for path in files if path.endswith(('.svg', '.png', '.webp', '.jpg', '.jpeg', '.avif'))]
    hero = next((path for path in images if 'hero' in path.lower()), 'src/assets/hero-art.svg')
    projects = [path for path in images if any(word in path.lower() for word in ('project', 'work', 'case'))][:3]
    projects += [f'src/assets/project-{i + 1}.svg' for i in range(len(projects), 3)]
    return {'task_type': 'website_generation', 'steps': STEPS, 'entrypoint': main, 'app': app,
            'expected_components': components, 'expected_sections': list(components), 'expected_ui': ui,
            'expected_assets': {'hero': hero, 'portfolio': projects},
            'expected_files': ['package.json', 'index.html', existing(['vite.config.ts', 'vite.config.js', 'vite.config.mts', 'vite.config.mjs']), main, app, *components.values(), *ui.values(), *styles, *data, hero, *projects, 'README.md'],
            'content_requirements': list(COMPONENTS), 'quality_target': 'production_polished'}


@dataclass
class WebsiteCompletionContract:
    checks: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def check(self, name, passed, feedback):
        self.checks[name] = bool(passed)
        if not passed: self.errors.append(feedback)

    @property
    def passed(self): return bool(self.checks) and all(self.checks.values())

    def report(self):
        return {'validator': 'WebsiteCompletionContract', 'checks': self.checks, 'passed': self.passed,
                'retryable': not self.passed, 'warnings': [], 'feedback': '\n'.join(self.errors)}

    async def inspect(self, read, plan, react=True):
        sources, asset_paths = {}, {}
        for path in plan['expected_files']:
            sources[path] = await read(path)
            if not sources[path] and path.startswith('src/assets/') and path.endswith('.svg'):
                for extension in ('.png', '.jpg', '.jpeg', '.webp', '.avif'):
                    alternative = str(PurePosixPath(path).with_suffix(extension))
                    asset = await read(alternative)
                    if asset:
                        sources[path] = sources[alternative] = asset
                        asset_paths[path] = alternative
                        break
            self.check('file:' + path, bool(sources[path].strip()), 'Create planned file: ' + path)
        if not react: return sources
        try:
            package = json.loads(sources.get('package.json') or '{}')
            deps = {**package.get('dependencies', {}), **package.get('devDependencies', {})}
            self.check('manifest', all(name in deps for name in ('react', 'react-dom', 'vite')), 'Declare React, React DOM and Vite dependencies.')
            self.check('build_script', 'vite build' in package.get('scripts', {}).get('build', ''), 'Add a build script in package.json.')
        except (ValueError, TypeError, AttributeError):
            self.check('manifest', False, 'Repair invalid package.json.')
        visited = set()
        imported_names = {}
        async def visit(path):
            if path in visited: return
            visited.add(path)
            content = sources.get(path) or await read(path)
            sources[path] = content
            for match in IMPORTS.finditer(content):
                spec = match.group(1)
                if spec.startswith(('@/', '~/')):
                    base = 'src/' + spec[2:]
                elif spec.startswith('.'):
                    base = str(PurePosixPath(path).parent / spec)
                else: continue
                # Normalize local imports without touching the host filesystem.
                parts = []
                for part in PurePosixPath(base).parts:
                    if part == '..':
                        if parts: parts.pop()
                    elif part != '.': parts.append(part)
                base = '/'.join(parts)
                candidates = [base] + [base + suffix for suffix in ('.jsx', '.tsx', '.js', '.ts', '.css', '/index.jsx', '/index.tsx', '/index.js', '/index.ts')]
                found = None
                for candidate in candidates:
                    source = sources.get(candidate) or await read(candidate)
                    if source:
                        sources[candidate] = source; found = candidate; break
                self.check('import:' + path + ':' + spec, found is not None, f'Repair unresolved import {spec} in {path}.')
                if found:
                    names = re.findall(r'\bimport\s+([A-Za-z_$][\w$]*)|\bas\s+([A-Za-z_$][\w$]*)|\{\s*([A-Za-z_$][\w$]*)', match.group(0))
                    imported_names.setdefault(found, set()).update(name for group in names for name in group if name)
                    await visit(found)
        await visit(plan['entrypoint'])
        html = sources.get('index.html', '')
        self.check('html_entrypoint', plan['entrypoint'] in html, 'Wire the planned entrypoint from index.html.')
        self.check('app_wired', plan['app'] in visited, 'Import and render the planned App from the entrypoint.')
        for name, path in {**plan['expected_components'], **plan.get('expected_ui', {})}.items():
            stem = PurePosixPath(path).stem
            render_patterns = [r'<\s*' + re.escape(binding) + r'\b' for binding in {stem, name, *imported_names.get(path, set())}]
            rendered = any(re.search(pattern, text) for source_path, text in sources.items() if source_path in visited and source_path != path for pattern in render_patterns)
            self.check('wired:' + name, path in visited and rendered, f'Import and render planned {name} component ({path}).')
        for path in plan['expected_files']:
            if path.endswith(('.css',)) or path.startswith('src/data/') or path in plan.get('expected_ui', {}).values() or path.startswith('src/assets/'):
                self.check('wired:' + path, asset_paths.get(path, path) in visited, 'Wire planned styles/content into the application: ' + path)
        return sources
