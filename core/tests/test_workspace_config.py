from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.workspace_config import (
    WorkspaceConfigError,
    load_workspace_config,
    supported_agents,
    update_supported_agents,
    validate_workspace_config,
)
from lab.model import VALID_AGENTS


def _valid_doc() -> dict:
    """The illustrative configuration from docs/workspace-architecture.md."""
    return {
        "version": 1,
        "id": "trust-safety",
        "name": "Trust & Safety",
        "agents": {
            "supported": ["claude", "codex", "copilot"],
            "default": "codex",
            "projections": [
                {"source": "agents/instructions.md", "target": "AGENTS.md", "mode": "symlink"},
                {"source": "agents/instructions.md", "target": "CLAUDE.md", "mode": "symlink", "when": "claude"},
            ],
        },
        "project": {
            "template": "templates/project",
            "features": ["tasks", "docs", "notebooks"],
            "mounts": [
                {"source": "skills", "target": ".agents/skills", "mode": "symlink"},
            ],
        },
        "notebooks": {
            "enabled": True,
            "provider": "darwin",
            "kernels": ["python3", "pyspark"],
            "mounts": [{"source": "code", "target": "code"}],
        },
        "display": {
            "autoOpen": ["docs", "notebooks"],
            "hide": ["worktrees"],
            "showProjectionOrigin": True,
        },
        "repositories": [],
        "services": [],
    }


# ── validate_workspace_config ────────────────────────────────────────────────

def test_doc_example_is_valid() -> None:
    errors, warnings = validate_workspace_config(_valid_doc())
    assert errors == []
    assert warnings == []


def test_missing_version_is_error() -> None:
    doc = _valid_doc()
    del doc["version"]
    errors, _ = validate_workspace_config(doc)
    assert any("version" in e for e in errors)


def test_newer_version_is_warning_not_error() -> None:
    doc = _valid_doc()
    doc["version"] = 2
    errors, warnings = validate_workspace_config(doc)
    assert errors == []
    assert any("version" in w for w in warnings)


def test_unknown_top_level_key_is_warning() -> None:
    doc = _valid_doc()
    doc["future_field"] = {"x": 1}
    errors, warnings = validate_workspace_config(doc)
    assert errors == []
    assert any("future_field" in w for w in warnings)


def test_bad_projection_mode_is_error() -> None:
    doc = _valid_doc()
    doc["agents"]["projections"][0]["mode"] = "hardlink"
    errors, _ = validate_workspace_config(doc)
    assert any("mode" in e and "hardlink" in e for e in errors)


def test_projection_missing_target_is_error() -> None:
    doc = _valid_doc()
    del doc["agents"]["projections"][0]["target"]
    errors, _ = validate_workspace_config(doc)
    assert any("target" in e for e in errors)


def test_default_agent_not_in_supported_is_error() -> None:
    doc = _valid_doc()
    doc["agents"]["default"] = "gemini"
    errors, _ = validate_workspace_config(doc)
    assert any("agents.default" in e for e in errors)


def test_when_agent_not_in_supported_is_warning() -> None:
    doc = _valid_doc()
    doc["agents"]["projections"][1]["when"] = "gemini"
    errors, warnings = validate_workspace_config(doc)
    assert errors == []
    assert any("when" in w for w in warnings)


def test_non_object_document_is_error() -> None:
    errors, _ = validate_workspace_config(["not", "an", "object"])
    assert errors


# ── load_workspace_config ────────────────────────────────────────────────────

def test_missing_file_is_absent_and_valid(tmp_path: Path) -> None:
    result = load_workspace_config(tmp_path)
    assert result["present"] is False
    assert result["valid"] is True
    assert result["errors"] == []


def test_invalid_json_is_present_and_invalid(tmp_path: Path) -> None:
    (tmp_path / "workspace.json").write_text("{nope", encoding="utf-8")
    result = load_workspace_config(tmp_path)
    assert result["present"] is True
    assert result["valid"] is False
    assert result["errors"]


def test_valid_file_round_trips(tmp_path: Path) -> None:
    (tmp_path / "workspace.json").write_text(json.dumps(_valid_doc()), encoding="utf-8")
    result = load_workspace_config(tmp_path)
    assert result["present"] is True
    assert result["valid"] is True
    assert result["config"]["id"] == "trust-safety"


def test_supported_agents_defaults_to_every_known_agent(tmp_path: Path) -> None:
    assert supported_agents(tmp_path) == list(VALID_AGENTS)


def test_update_supported_agents_preserves_config_and_clamps_default(tmp_path: Path) -> None:
    doc = _valid_doc()
    (tmp_path / "workspace.json").write_text(json.dumps(doc), encoding="utf-8")

    result = update_supported_agents(tmp_path, ["codex"], "claude")

    assert result["valid"] is True
    saved = result["config"]
    assert saved["agents"]["supported"] == ["codex"]
    assert saved["agents"]["default"] == "codex"
    assert saved["agents"]["projections"] == doc["agents"]["projections"]
    assert saved["notebooks"] == doc["notebooks"]


def test_update_supported_agents_rejects_empty_or_broken_config(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceConfigError, match="at least one"):
        update_supported_agents(tmp_path, [], "claude")

    (tmp_path / "workspace.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(WorkspaceConfigError, match="repaired"):
        update_supported_agents(tmp_path, ["codex"], "claude")
    assert (tmp_path / "workspace.json").read_text(encoding="utf-8") == "{broken"


# ── HTTP surface ─────────────────────────────────────────────────────────────

def test_workspaces_payload_reports_config_status(client, monorepo: Path) -> None:
    (monorepo / "workspace.json").write_text(json.dumps(_valid_doc()), encoding="utf-8")

    r = client.get("/api/workspaces")

    assert r.status_code == 200, r.text
    config = r.json()["current"]["config"]
    assert config["present"] is True
    assert config["valid"] is True
    # summary payload stays small: no parsed document in the list endpoint
    assert "config" not in config


def test_workspace_config_endpoint_returns_document(client, monorepo: Path) -> None:
    (monorepo / "workspace.json").write_text(json.dumps(_valid_doc()), encoding="utf-8")

    r = client.get("/api/workspace/config")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["present"] is True
    assert body["valid"] is True
    assert body["config"]["agents"]["default"] == "codex"


def test_workspace_config_endpoint_without_file(client, monorepo: Path) -> None:
    r = client.get("/api/workspace/config")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["present"] is False
    assert body["valid"] is True


def test_workspace_config_endpoint_flags_broken_file(client, monorepo: Path) -> None:
    (monorepo / "workspace.json").write_text("{broken", encoding="utf-8")

    r = client.get("/api/workspace/config")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["present"] is True
    assert body["valid"] is False
    assert body["errors"]


def test_workspace_config_init_creates_starter(client, monorepo: Path) -> None:
    r = client.post("/api/workspace/config/init")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["present"] is True
    assert body["valid"] is True
    assert body["config"]["version"] == 1
    assert body["config"]["agents"]["default"] in body["config"]["agents"]["supported"]
    doc = json.loads((monorepo / "workspace.json").read_text())
    assert doc["version"] == 1

    # Bootstrap only: a second call refuses to overwrite.
    r = client.post("/api/workspace/config/init")
    assert r.status_code == 409


def test_workspace_agents_endpoint_updates_policy_and_rejects_last_removal(
    client, monorepo: Path,
) -> None:
    r = client.post("/api/workspace/agents", json={"supported": ["codex"]})

    assert r.status_code == 200, r.text
    assert r.json()["supported"] == ["codex"]
    assert r.json()["default"] == "codex"
    saved = json.loads((monorepo / "workspace.json").read_text(encoding="utf-8"))
    assert saved["agents"]["supported"] == ["codex"]
    assert saved["agents"]["default"] == "codex"

    fetched = client.get("/api/workspace/agents")
    assert fetched.status_code == 200
    assert fetched.json()["supported"] == ["codex"]

    rejected = client.post("/api/workspace/agents", json={"supported": []})
    assert rejected.status_code == 400
    assert "at least one" in rejected.json()["detail"]
    assert json.loads((monorepo / "workspace.json").read_text())["agents"]["supported"] == ["codex"]


def test_disabled_agent_is_rejected_by_settings_and_project_override(
    client, monorepo: Path, seed_project,
) -> None:
    doc = _valid_doc()
    doc["agents"]["supported"] = ["codex"]
    doc["agents"]["default"] = "codex"
    (monorepo / "workspace.json").write_text(json.dumps(doc), encoding="utf-8")
    seed_project("demo")

    settings = client.post("/api/settings", json={"defaultAgent": "claude"})
    assert settings.status_code == 400
    assert "not enabled" in settings.json()["detail"]

    project = client.post("/api/projects/demo/agent", json={"agent": "claude"})
    assert project.status_code == 400
    assert "not enabled" in project.json()["detail"]

    enabled = client.post("/api/projects/demo/agent", json={"agent": "codex"})
    assert enabled.status_code == 200, enabled.text
