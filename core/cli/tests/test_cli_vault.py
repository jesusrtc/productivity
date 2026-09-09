from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from lab import paths
from lab.cli import main


def _write_framework_checkout(root: Path) -> None:
    (root / ".git").mkdir(parents=True)
    (root / "content").mkdir()
    (root / "core" / "cli" / "src" / "lab").mkdir(parents=True)
    (root / "core" / "src" / "core").mkdir(parents=True)
    (root / "Makefile").write_text("install:\n")


def test_lab_init_creates_vault_and_registers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home"))
    vault = tmp_path / "my-lab"
    result = CliRunner().invoke(main, ["init", str(vault), "--no-git"])
    assert result.exit_code == 0, result.output

    assert (vault / "lab.toml").is_file()
    assert (vault / "workspaces" / "example" / "workspace.json").is_file()
    assert (vault / "apps" / "example-cli" / "lab-app.toml").is_file()
    assert (vault / "content" / "README.md").is_file()
    assert "lab notebook exec" in (vault / "AGENTS.md").read_text()
    assert (vault / "repositories" / ".gitignore").read_text() == "*\n!.gitignore\n!README.md\n"
    assert (vault / ".lab" / "state" / "indexes").is_dir()

    registry = paths.read_vault_registry()
    assert registry["active"] == "my-lab"
    assert registry["vaults"][0]["path"] == str(vault.resolve())


def test_vault_use_and_current(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home"))
    vault = tmp_path / "work"
    CliRunner().invoke(main, ["init", str(vault), "--no-git", "--no-example"])

    result = CliRunner().invoke(main, ["vault", "use", str(vault)])
    assert result.exit_code == 0, result.output
    assert "active vault" in result.output

    monkeypatch.delenv("LAB_ROOT", raising=False)
    monkeypatch.delenv("LAB_VAULT", raising=False)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["vault", "current"])
    assert result.exit_code == 0, result.output
    assert str(vault.resolve()) in result.output


def test_find_vault_root_prefers_lab_vault(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home"))
    a = tmp_path / "a"
    b = tmp_path / "b"
    CliRunner().invoke(main, ["init", str(a), "--no-git", "--no-example"])
    CliRunner().invoke(main, ["init", str(b), "--no-git", "--no-example"])
    monkeypatch.setenv("LAB_VAULT", str(a))
    assert paths.find_vault_root() == a.resolve()


def test_find_vault_root_uses_registry_from_framework_checkout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home"))
    framework = tmp_path / "framework"
    _write_framework_checkout(framework)
    vault = tmp_path / "vault"
    CliRunner().invoke(main, ["init", str(vault), "--no-git", "--no-example"])

    monkeypatch.delenv("LAB_ROOT", raising=False)
    monkeypatch.delenv("LAB_VAULT", raising=False)
    monkeypatch.chdir(framework)

    assert paths.find_vault_root() == vault.resolve()


def test_find_framework_root_detects_core_cli_checkout(tmp_path: Path, monkeypatch) -> None:
    framework = tmp_path / "framework"
    _write_framework_checkout(framework)
    monkeypatch.delenv("LAB_FRAMEWORK_ROOT", raising=False)

    assert paths.find_framework_root(framework / "core" / "cli" / "src" / "lab") == framework.resolve()


def test_app_list_and_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home"))
    vault = tmp_path / "my-lab"
    CliRunner().invoke(main, ["init", str(vault), "--no-git"])
    monkeypatch.setenv("LAB_VAULT", str(vault))

    result = CliRunner().invoke(main, ["app", "list"])
    assert result.exit_code == 0, result.output
    assert "example-cli" in result.output

    called: list[dict] = []

    def fake_run(cmd, cwd=None):
        called.append({"cmd": cmd, "cwd": cwd})
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("lab.commands.app.subprocess.run", fake_run)
    result = CliRunner().invoke(main, ["app", "run", "example-cli"])
    assert result.exit_code == 0, result.output
    assert called
    assert called[0]["cmd"][0] == str(vault / "apps" / "example-cli" / "bin" / "example")
