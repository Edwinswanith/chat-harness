import asyncio

import pytest

from app.workspaces.provider import LocalWorkspaceProvider
from app.tools.tool_registry import ToolRegistry
from app.tools.create_artifact import CreateArtifact
from app.core.config import Settings
from app.workspaces.website_workflow import WebsiteWorkflow
from app.harness.run_state import transition_allowed


def test_workspace_provider_enforces_root_and_sensitive_file_boundary(tmp_path):
    asyncio.run(scenario(tmp_path))


async def scenario(tmp_path):
    root, outside = tmp_path / "project", tmp_path / "outside.txt"
    root.mkdir(); (root / "src").mkdir(); (root / "src" / "app.txt").write_text("hello workspace")
    (root / ".env").write_text("secret"); outside.write_text("outside")
    provider = LocalWorkspaceProvider({"project": str(root)})
    assert (await provider.read_file("project", "src/app.txt"))["content"] == "hello workspace"
    assert (await provider.search_text("project", "hello"))[0]["path"] == "src/app.txt"
    with pytest.raises(ValueError): await provider.read_file("project", "../outside.txt")
    with pytest.raises(ValueError): await provider.read_file("project", ".env")
    await provider.write_file("project", ".env.example", "MONGODB_URI=mongodb://localhost/app", create=True)
    await provider.write_file("project", "src/new.txt", "new", create=True)
    assert (await provider.create_directory("project", "src"))["existed"] is True
    await provider.create_directory("project", "docs")
    await provider.rename_path("project", "src/new.txt", "docs/renamed.txt")
    assert (root / "docs" / "renamed.txt").read_text() == "new"
    await provider.delete_path("project", "docs/renamed.txt")
    assert not (root / "docs" / "renamed.txt").exists()
    with pytest.raises(ValueError): await provider.write_file("project", "../escape.txt", "no")
    with pytest.raises(ValueError): await provider.delete_path("project", ".")


def test_workspace_scan_is_metadata_only_and_honors_ignore_files(tmp_path):
    async def check():
        root = tmp_path / "project"; root.mkdir()
        (root / "visible.ts").write_text("export const app = true")
        (root / "ignored.txt").write_text("do not index")
        (root / ".gitignore").write_text("ignored.txt\n")
        (root / "node_modules").mkdir(); (root / "node_modules" / "package.js").write_text("ignored")
        files = await LocalWorkspaceProvider({"project": str(root)}).scan_files("project")
        paths = {item["relative_path"] for item in files}
        assert "visible.ts" in paths
        assert "ignored.txt" not in paths and "node_modules/package.js" not in paths
        assert next(item for item in files if item["relative_path"] == "visible.ts")["language"] == "typescript"
    asyncio.run(check())


def test_workspace_mode_does_not_offer_report_artifact_tool():
    registry = ToolRegistry([CreateArtifact(None, None)])
    assert registry.describe("workspace") == []
    assert registry.describe("chatbot")[0]["name"] == "create_artifact"


def test_workspace_step_budget_is_large_enough_for_multifile_projects():
    settings = Settings()
    assert settings.workspace_max_steps > settings.max_steps
    assert settings.workspace_max_steps >= 24


def test_website_task_classification_requires_browser_and_visual_validation():
    classified = WebsiteWorkflow.classify("Build an aesthetic professional business portfolio website in React")
    assert classified["task_type"] == "website_generation"
    assert classified["visual_quality_required"] is True
    assert classified["browser_validation_required"] is True
    assert WebsiteWorkflow.classify("Create an Express API")["visual_quality_required"] is False


def test_workspace_visual_workflow_builds_context_before_inspection():
    """A visual task must never attempt the invalid coding -> context transition."""
    assert transition_allowed("planning", "context_building")
    assert transition_allowed("context_building", "inspecting_workspace")
    assert transition_allowed("inspecting_workspace", "designing")
    assert transition_allowed("designing", "coding")
    assert not transition_allowed("coding", "context_building")
