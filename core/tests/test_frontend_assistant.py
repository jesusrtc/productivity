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


def test_assistant_view_has_minimal_lists_modal_and_copy_actions() -> None:
    source = ASSISTANT_APP.read_text(encoding="utf-8")
    assert "Recently completed" in source
    assert "Any priority" in source
    assert "Ready to review" in source
    assert "Follow up" in source
    assert "Nudge" in source
    assert "Proposal 1 · Filter strip" in source
    assert "Proposal 2 · Focus queue" in source
    assert "Proposal 3 · Project ledger" in source
    assert 'class="assistant-compact-row"' in source
    assert "button.addEventListener('dblclick'" in source
    assert "assistantDocumentModal" in source
    assert "Meeting notes" in source
    assert "assistant-subtasks" in source
    assert "data-assistant-subtask" in source
    assert "'/api/assistant/subtask?path='" in source
    assert "window.marked.parse" in source
    assert "slack.textContent = 'Slack'" in source
    assert "gdoc.textContent = 'GDoc'" in source
    assert "/api/assistant/asset" in source
    assert 'data-assistant-generate=' in source
    assert "copy.textContent = 'Copy content'" in source
    assert "plain.textContent = 'Plain text'" in source
    assert "assistant-preview-image" in source
    assert "Open project" not in source


def test_assistant_repo_tabs_include_tasks_and_meeting_notes() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    assert 'data-assistant-section="tasks-1"' in source
    assert 'data-assistant-section="tasks-2"' in source
    assert 'data-assistant-section="tasks-3"' in source
    assert 'data-assistant-section="meetings"' in source
    assert "AssistantView.setSection('tasks-1')" in source
    assert "AssistantView.setSection('tasks-2')" in source
    assert "AssistantView.setSection('tasks-3')" in source
    assert "AssistantView.setSection('meetings')" in source
