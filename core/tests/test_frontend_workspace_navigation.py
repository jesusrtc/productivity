from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAB_APP = ROOT / "core/src/core/static/js/lab-app.js"


def test_workspace_subnavigation_does_not_render_repository_buttons() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    start = source.index("function renderRepoTabs()")
    end = source.index("function showScopedCodeSearch()", start)
    render = source[start:end]

    workspace = render[render.index('} else if (currentWorkspace.is_workspace)'):render.index('// One tab per declared server')]
    assert 'LabObjectives?.tabsHtml' in workspace
    assert "Overview" not in workspace and "Code Search" not in workspace and "Jupyter" not in workspace
    assert "openWorkspaceProxy" in render
    assert "selectWorkspaceRepo" not in render
    assert "currentWorkspace.repos" not in render
