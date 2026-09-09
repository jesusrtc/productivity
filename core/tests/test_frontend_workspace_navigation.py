from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAB_APP = ROOT / "core/src/core/static/js/lab-app.js"


def test_workspace_subnavigation_does_not_render_repository_buttons() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    start = source.index("function renderRepoTabs()")
    end = source.index("function showScopedCodeSearch()", start)
    render = source[start:end]

    assert "Overview" in render
    assert "Code Search" in render
    assert "openWorkspaceProxy" in render
    assert "selectWorkspaceRepo" not in render
    assert "currentWorkspace.repos" not in render
