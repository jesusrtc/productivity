from __future__ import annotations

from click.testing import CliRunner

from lab.cli import main


def test_start_invokes_make(monkeypatch) -> None:
    called: list[list[str]] = []

    def fake_run(cmd, check, cwd=None):
        called.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("lab.commands.service.subprocess.run", fake_run)
    result = CliRunner().invoke(main, ["start"])
    assert result.exit_code == 0, result.output
    assert called and called[0][:2] == ["make", "start-bg"]


def test_stop_invokes_make(monkeypatch) -> None:
    called: list[list[str]] = []

    def fake_run(cmd, check, cwd=None):
        called.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("lab.commands.service.subprocess.run", fake_run)
    result = CliRunner().invoke(main, ["stop"])
    assert result.exit_code == 0
    assert called and called[0][:2] == ["make", "stop"]


def test_open_calls_webbrowser(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("lab.commands.service.webbrowser.open", lambda u: opened.append(u))
    result = CliRunner().invoke(main, ["open"])
    assert result.exit_code == 0
    assert opened == ["http://localhost:3333/api/index"]
