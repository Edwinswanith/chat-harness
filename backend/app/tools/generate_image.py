import base64

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.contracts import ToolResult


class ImageArguments(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)

    relative_path: str | None = Field(default=None, max_length=500, description="Optional workspace-local PNG/JPEG asset path. Existing assets are never overwritten.")

    @field_validator('relative_path')
    @classmethod
    def asset_extension(cls, value):
        from pathlib import PurePosixPath
        if value is not None and PurePosixPath(value).suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
            raise ValueError('Generated local asset path must use PNG or JPEG; use workspace_create_file for SVG artwork')
        return value

    model_config = ConfigDict(extra="forbid")


class GenerateImage:
    name = "generate_image"
    description = "Generate a Gemini PNG/JPEG image or company logo. Workspace mode always saves into the selected project, even without relative_path; then import/render the returned path in the website."
    schema = ImageArguments

    def __init__(self, images, artifacts, workspaces=None):
        self.images, self.artifacts, self.workspaces = images, artifacts, workspaces

    async def execute(self, scope, run, arguments):
        destination = arguments.relative_path
        workspace_mode = run.get('mode') == 'workspace'
        if workspace_mode and not self.workspaces: raise ValueError('Workspace image generation is unavailable')
        if workspace_mode:
            workspace = await self.workspaces.get(scope, run['project_workspace_id'])
            root = self.workspaces.provider.root(workspace['root_id'])
            if not workspace['settings'].get('allow_file_creation'): raise ValueError('Workspace file creation is disabled')
        if destination:
            if run.get('mode') != 'workspace' or not self.workspaces: raise ValueError('Local assets require a selected workspace')
            workspace = await self.workspaces.get(scope, run['project_workspace_id'])
            if not workspace['settings'].get('allow_file_creation'): raise ValueError('Workspace file creation is disabled')
            path = self.workspaces.provider.mutable_path(workspace['root_id'], destination)
            if path.suffix.lower() not in {'.png', '.jpg', '.jpeg'}: raise ValueError('Image asset must be PNG or JPEG')
            if path.exists(): raise ValueError('Asset already exists; choose a new asset path')
        name, data = await self.images.generate(arguments.prompt)
        if workspace_mode and not destination:
            from uuid import uuid4
            from pathlib import PurePosixPath
            stem = 'company-logo' if 'logo' in arguments.prompt.lower() else 'generated-image'
            folder = 'src/assets/generated' if (root / 'src').is_dir() else 'assets/generated'
            destination = f'{folder}/{stem}-{uuid4().hex[:8]}{PurePosixPath(name).suffix}'
            path = self.workspaces.provider.mutable_path(workspace['root_id'], destination)
        if destination:
            import hashlib
            if path.suffix.lower() != '.png' and name.endswith('.png') or path.suffix.lower() == '.png' and not name.endswith('.png'):
                raise ValueError('Generated image format does not match the requested extension; use a matching path')
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle: handle.write(data)
            change = {'path': destination, 'created': True, 'after_sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data), 'operation': 'create'}
            await self.workspaces.repo.create('workspace_change', scope, '', project_workspace_id=run['project_workspace_id'], run_id=run['id'], tool_run_id=run.get('tool_run_id'), **change)
            return ToolResult(status='success', data={**change, 'image': destination, 'integration_required': (root / 'index.html').is_file() or (root / 'src').is_dir(), 'next_action': 'Import this local asset and render it in the requested website location. Use the saved path; do not generate another copy.'})
        artifact = await self.artifacts.publish(scope, run, {
            "name": name, "content_base64": base64.b64encode(data).decode()}, [])
        return ToolResult(status="success", artifact_ids=[artifact["id"]], data={"image": artifact["name"]})
