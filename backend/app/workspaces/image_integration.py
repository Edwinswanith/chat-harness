"""Require generated website imagery to be wired before claiming delivery."""
import posixpath
import re


async def integration_feedback(workspaces, scope, workspace_id, images):
    required = [item['path'] for item in images if item.get('integration_required')]
    if not required: return ''
    files = (await workspaces.inspect(scope, workspace_id))['files']
    wired, sources = set(), {}
    for path in files:
        if not path.endswith(('.jsx', '.tsx', '.js', '.ts', '.css', '.html')): continue
        try: source = (await workspaces.read(scope, workspace_id, path))['content']
        except (KeyError, ValueError): continue
        sources[path] = source
    def resolve(path, spec):
        base = spec.lstrip('/') if spec.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
        return next((candidate for candidate in [base, *[base + ext for ext in ('.jsx','.tsx','.js','.ts','.css','/index.jsx','/index.tsx')]] if candidate in sources), None)
    entries = [path for path in ('index.html','src/main.jsx','src/main.tsx','src/index.jsx','src/index.tsx') if path in sources]
    if not entries and 'src/App.jsx' in sources: entries = ['src/App.jsx']
    if not entries and 'src/App.tsx' in sources: entries = ['src/App.tsx']
    reachable, queue = set(), list(entries)
    while queue:
        path = queue.pop()
        if path in reachable: continue
        reachable.add(path)
        source = sources[path]
        for match in re.finditer(r'''(?:import\s+(?:(\w+)\s+from\s*)?|(?:src|href)\s*=|url\(\s*)["']([^"']+)["']''', source):
            binding, spec = match.groups()
            target = resolve(path, spec)
            if target is None: continue
            if binding and binding[0].isupper() and target.endswith(('.jsx','.tsx')) and not re.search(r'<\s*' + re.escape(binding) + r'\b|createElement\(\s*' + re.escape(binding), source): continue
            queue.append(target)
    for path in reachable:
        source = sources[path]
        for asset in required:
            for ref in re.finditer(r'''["']([^"']+)["']''', source):
                spec = ref.group(1)
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
                if spec.startswith('/'): resolved = spec.lstrip('/')
                if resolved != asset and ('public/' + resolved) != asset: continue
                if path.endswith(('.html', '.css')):
                    if re.search(r'(?:src\s*=|url\(\s*)["\']?' + re.escape(spec), source): wired.add(asset)
                else:
                    binding = re.search(r'import\s+(\w+)\s+from\s+["\']' + re.escape(spec) + r'["\']', source)
                    if binding and re.search(r'(?:src\s*=\s*\{\s*|url\([^)]*)' + re.escape(binding.group(1)), source): wired.add(asset)
    missing = [path for path in required if path not in wired]
    return ('Generated images are saved but not rendered in the website: ' + ', '.join(missing)
        + '. Import and render these existing assets in the requested components, then run the build. Do not generate duplicates.') if missing else ''
