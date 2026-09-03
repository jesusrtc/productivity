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
    assert "Any priority" in source
    assert "Nudge" in source
    assert "Lab projects" in source
    assert "assistant-internal-projects" in source
    assert "data-assistant-group" in source
    assert "attentionBreakdown" in source
    assert "needsAttention" in source
    assert "isDueSoon" in source
    assert "assistant-row-tldr" in source
    assert 'class="assistant-compact-row' in source
    assert "openDocumentModal(kind, path)" in source
    assert "assistantDocumentModal" in source
    assert "assistantDocumentNav" in source
    assert "Main task" in source
    assert "Subtask" in source
    assert "data-assistant-modal-document" in source
    assert "Copy for Google Docs" in source
    assert "Copy plain text" in source
    assert "Meeting notes" in source
    assert "'/api/assistant/subtask?path='" in source
    assert "window.marked.parse" in source
    assert "slack.textContent = 'Slack'" in source
    assert "gdoc.textContent = 'GDoc'" in source
    assert "/api/assistant/asset" in source
    assert "copy.textContent = 'Copy content'" in source
    assert "plain.textContent = 'Plain text'" in source
    assert "Open project" not in source


def test_assistant_repo_tabs_include_tasks_and_meeting_notes() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    assert 'data-assistant-section="tasks"' in source
    assert 'data-assistant-section="meetings"' in source
    assert "AssistantView.setSection('tasks')" in source
    assert "AssistantView.setSection('meetings')" in source
    assert 'data-assistant-section="tasks-1"' not in source
