from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAB_APP = ROOT / "core/src/core/static/js/lab-app.js"
ASSISTANT_APP = ROOT / "core/src/core/static/js/views/assistant.js"


def test_assistant_is_permanent_tab_immediately_after_home() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    home = source.index("&#x1F3E0; Home")
    assistant = source.index("&#x2726; Assistant", home)
    workspace_tabs = source.index("workspaceTabs.map", home)
    assert home < assistant < workspace_tabs


def test_assistant_navigation_and_terminal_are_global() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    assert "const ASSISTANT_PROJECT_ID = '__assistant__'" in source
    assert "const ASSISTANT_WORKSPACE_ID = '__assistant__'" in source
    assert "function goToAssistant" in source
    assert "function termOpenForAssistant" in source
    assert "workspace_id: ASSISTANT_WORKSPACE_ID" in source


def test_assistant_view_has_filters_markdown_and_copy_actions() -> None:
    source = ASSISTANT_APP.read_text(encoding="utf-8")
    assert "Recently completed" in source
    assert "All priorities" in source
    assert "window.marked.parse" in source
    assert "slack.textContent = 'Slack'" in source
    assert "gdoc.textContent = 'GDoc'" in source
    assert "/api/assistant/asset" in source
