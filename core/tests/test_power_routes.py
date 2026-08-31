from __future__ import annotations

import subprocess
import time

from fastapi import HTTPException

from core.routes import power


def _configure_supported_timer(monkeypatch, tmp_path):
    deadline_file = tmp_path / "lid-awake.deadline"
    starts: list[str] = []
    monkeypatch.setattr(power, "_deadline_path", lambda: deadline_file)
    monkeypatch.setattr(power, "_is_supported", lambda: True)
    monkeypatch.setattr(
        power, "_start_privileged_timer",
        lambda **_kwargs: starts.append("start"),
    )
    return deadline_file, starts


def test_lid_awake_starts_renews_and_cancels(client, monkeypatch, tmp_path) -> None:
    deadline_file, starts = _configure_supported_timer(monkeypatch, tmp_path)

    initial = client.get("/api/power/lid-awake")
    assert initial.status_code == 200
    assert initial.json() == {
        "supported": True,
        "active": False,
        "deadline": None,
        "remaining_seconds": 0,
    }

    started = client.post("/api/power/lid-awake", json={"minutes": 15})
    assert started.status_code == 200
    assert started.json()["active"] is True
    assert 898 <= started.json()["remaining_seconds"] <= 900
    assert starts == ["start"]
    first_deadline = int(deadline_file.read_text())

    renewed = client.post("/api/power/lid-awake", json={"minutes": 60})
    assert renewed.status_code == 200
    assert renewed.json()["active"] is True
    assert 3598 <= renewed.json()["remaining_seconds"] <= 3600
    assert int(deadline_file.read_text()) > first_deadline
    assert starts == ["start"]  # renewal reuses the existing root helper

    cancelled = client.delete("/api/power/lid-awake")
    assert cancelled.status_code == 200
    assert cancelled.json()["active"] is False
    assert not deadline_file.exists()


def test_lid_awake_rejects_other_durations(client, monkeypatch, tmp_path) -> None:
    _configure_supported_timer(monkeypatch, tmp_path)
    response = client.post("/api/power/lid-awake", json={"minutes": 20})
    assert response.status_code == 422


def test_lid_awake_clears_deadline_when_approval_is_cancelled(
    client, monkeypatch, tmp_path,
) -> None:
    deadline_file, _starts = _configure_supported_timer(monkeypatch, tmp_path)

    def cancelled(**_kwargs) -> None:
        raise HTTPException(
            status_code=409,
            detail="Administrator approval was cancelled. Lid Awake was not started.",
        )

    monkeypatch.setattr(power, "_start_privileged_timer", cancelled)
    response = client.post("/api/power/lid-awake", json={"minutes": 15})
    assert response.status_code == 409
    assert "cancelled" in response.json()["detail"]
    assert not deadline_file.exists()


def test_lid_awake_is_mac_only(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(power, "_deadline_path", lambda: tmp_path / "deadline")
    monkeypatch.setattr(power, "_is_supported", lambda: False)

    status = client.get("/api/power/lid-awake")
    assert status.status_code == 200
    assert status.json()["supported"] is False
    response = client.post("/api/power/lid-awake", json={"minutes": 15})
    assert response.status_code == 501


def test_expired_deadline_is_cleaned_up(monkeypatch, tmp_path) -> None:
    deadline_file = tmp_path / "deadline"
    deadline_file.write_text(f"{int(time.time()) - 10}\n")
    monkeypatch.setattr(power, "_deadline_path", lambda: deadline_file)
    monkeypatch.setattr(power, "_is_supported", lambda: True)

    assert power._status()["active"] is False
    assert not deadline_file.exists()


def test_privileged_timer_uses_pmset_and_a_deadline_watcher(tmp_path) -> None:
    command = power._timer_helper_command(tmp_path / "deadline with spaces")
    assert command.startswith("/usr/bin/pmset -a disablesleep 1;")
    assert "/usr/bin/pmset -a disablesleep 0" in command
    assert "/bin/cat" in command
    assert "/bin/sleep 1" in command
    assert "/usr/bin/nohup /bin/sh -c" in command
    assert power._SUCCESS_MARKER in command
    assert subprocess.run(["/bin/sh", "-n", "-c", command]).returncode == 0


def test_privileged_timer_runs_sudo_in_a_private_terminal(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(power, "_deadline_path", lambda: tmp_path / "deadline")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=f"{power._SUCCESS_MARKER}\r\n"
        )

    monkeypatch.setattr(power.subprocess, "run", fake_run)
    power._start_privileged_timer(auth_method="touch_id")

    argv, kwargs = calls[0]
    assert argv[:4] == ["/usr/bin/script", "-q", "/dev/null", "/usr/bin/sudo"]
    assert "/usr/bin/osascript" not in argv
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["input"] is None
    assert kwargs["start_new_session"] is True


def test_privileged_timer_passes_password_only_through_stdin(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(power, "_deadline_path", lambda: tmp_path / "deadline")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=f"{power._SUCCESS_MARKER}\n"
        )

    monkeypatch.setattr(power.subprocess, "run", fake_run)
    password = "correct horse battery staple"
    power._start_privileged_timer(auth_method="password", password=password)

    argv, kwargs = calls[0]
    assert argv[:5] == ["/usr/bin/sudo", "-S", "-p", "", "--"]
    assert password not in argv
    assert kwargs["stdin"] is None
    assert kwargs["input"] == f"{password}\n"
    assert kwargs["start_new_session"] is True


def test_password_method_requires_a_password_for_a_new_timer(
    client, monkeypatch, tmp_path,
) -> None:
    deadline_file, starts = _configure_supported_timer(monkeypatch, tmp_path)

    response = client.post(
        "/api/power/lid-awake",
        json={"minutes": 15, "auth_method": "password"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Enter your Mac password."
    assert starts == []
    assert not deadline_file.exists()


def test_password_is_forwarded_for_a_new_timer(client, monkeypatch, tmp_path) -> None:
    deadline_file = tmp_path / "lid-awake.deadline"
    calls = []
    monkeypatch.setattr(power, "_deadline_path", lambda: deadline_file)
    monkeypatch.setattr(power, "_is_supported", lambda: True)
    monkeypatch.setattr(
        power, "_start_privileged_timer", lambda **kwargs: calls.append(kwargs),
    )

    response = client.post(
        "/api/power/lid-awake",
        json={
            "minutes": 15,
            "auth_method": "password",
            "password": "one-time-secret",
        },
    )

    assert response.status_code == 200
    assert calls == [{"auth_method": "password", "password": "one-time-secret"}]


def test_active_timer_renews_without_another_password(client, monkeypatch, tmp_path) -> None:
    deadline_file, starts = _configure_supported_timer(monkeypatch, tmp_path)
    deadline_file.write_text(f"{int(time.time()) + 600}\n")

    response = client.post(
        "/api/power/lid-awake",
        json={"minutes": 30, "auth_method": "password"},
    )

    assert response.status_code == 200
    assert starts == []


def test_touch_id_failure_message_is_friendly(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(power, "_deadline_path", lambda: tmp_path / "deadline")
    monkeypatch.setattr(
        power.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout="sudo: no password was provided\r\n"
        ),
    )

    try:
        power._start_privileged_timer(auth_method="touch_id")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail == (
            "Touch ID was not approved. Confirm that sudo works with Touch ID "
            "in Terminal, then try again."
        )
    else:  # pragma: no cover - protects the assertion if the helper stops raising
        raise AssertionError("expected cancellation to raise HTTPException")


def test_password_failure_message_is_friendly(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(power, "_deadline_path", lambda: tmp_path / "deadline")
    monkeypatch.setattr(
        power.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout="Sorry, try again.\n"
        ),
    )

    try:
        power._start_privileged_timer(auth_method="password", password="wrong")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail == (
            "Password authentication failed. Check your Mac password and try again."
        )
    else:  # pragma: no cover
        raise AssertionError("expected failed authentication to raise HTTPException")
