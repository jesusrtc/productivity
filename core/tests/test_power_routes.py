from __future__ import annotations

import subprocess
import time

from fastapi import HTTPException

from core.routes import power


def _configure_supported_timer(monkeypatch, tmp_path):
    deadline_file = tmp_path / "lid-awake.deadline"
    starts: list[str] = []
    saved = {"password": None}
    monkeypatch.setattr(power, "_deadline_path", lambda: deadline_file)
    monkeypatch.setattr(power, "_is_supported", lambda: True)
    monkeypatch.setattr(
        power, "_start_privileged_timer",
        lambda *, password: starts.append(password),
    )
    monkeypatch.setattr(
        power, "_keychain_has_password", lambda: saved["password"] is not None,
    )
    monkeypatch.setattr(power, "_read_keychain_password", lambda: saved["password"])

    def save_password(password: str) -> bool:
        saved["password"] = password
        return True

    def delete_password() -> bool:
        saved["password"] = None
        return True

    monkeypatch.setattr(power, "_save_keychain_password", save_password)
    monkeypatch.setattr(power, "_delete_keychain_password", delete_password)
    return deadline_file, starts, saved


def test_lid_awake_starts_saves_renews_and_cancels(
    client, monkeypatch, tmp_path,
) -> None:
    deadline_file, starts, saved = _configure_supported_timer(monkeypatch, tmp_path)

    initial = client.get("/api/power/lid-awake")
    assert initial.status_code == 200
    assert initial.json() == {
        "supported": True,
        "active": False,
        "deadline": None,
        "remaining_seconds": 0,
        "password_saved": False,
    }

    started = client.post(
        "/api/power/lid-awake",
        json={"minutes": 15, "password": "one-time-secret"},
    )
    assert started.status_code == 200
    assert started.json()["active"] is True
    assert started.json()["password_saved"] is True
    assert 898 <= started.json()["remaining_seconds"] <= 900
    assert starts == ["one-time-secret"]
    assert saved["password"] == "one-time-secret"
    first_deadline = int(deadline_file.read_text())

    renewed = client.post("/api/power/lid-awake", json={"minutes": 60})
    assert renewed.status_code == 200
    assert renewed.json()["active"] is True
    assert 3598 <= renewed.json()["remaining_seconds"] <= 3600
    assert int(deadline_file.read_text()) > first_deadline
    assert starts == ["one-time-secret"]  # renewal reuses the root helper

    cancelled = client.delete("/api/power/lid-awake")
    assert cancelled.status_code == 200
    assert cancelled.json()["active"] is False
    assert cancelled.json()["password_saved"] is True
    assert not deadline_file.exists()


def test_lid_awake_rejects_other_durations(client, monkeypatch, tmp_path) -> None:
    _configure_supported_timer(monkeypatch, tmp_path)
    response = client.post("/api/power/lid-awake", json={"minutes": 20})
    assert response.status_code == 422


def test_lid_awake_clears_deadline_and_password_after_auth_failure(
    client, monkeypatch, tmp_path,
) -> None:
    deadline_file, _starts, saved = _configure_supported_timer(monkeypatch, tmp_path)

    def rejected(*, password: str) -> None:
        raise HTTPException(
            status_code=409,
            detail="Password authentication failed.",
        )

    monkeypatch.setattr(power, "_start_privileged_timer", rejected)
    response = client.post(
        "/api/power/lid-awake",
        json={"minutes": 15, "password": "wrong"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "Mac password did not work. Enter a new password.",
        "password_saved": False,
    }
    assert saved["password"] is None
    assert not deadline_file.exists()


def test_lid_awake_is_mac_only(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(power, "_deadline_path", lambda: tmp_path / "deadline")
    monkeypatch.setattr(power, "_is_supported", lambda: False)

    status = client.get("/api/power/lid-awake")
    assert status.status_code == 200
    assert status.json()["supported"] is False
    assert status.json()["password_saved"] is False
    response = client.post("/api/power/lid-awake", json={"minutes": 15})
    assert response.status_code == 501


def test_expired_deadline_is_cleaned_up(monkeypatch, tmp_path) -> None:
    deadline_file, _starts, _saved = _configure_supported_timer(monkeypatch, tmp_path)
    deadline_file.write_text(f"{int(time.time()) - 10}\n")

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
    power._start_privileged_timer(password=password)

    argv, kwargs = calls[0]
    assert argv[:6] == ["/usr/bin/sudo", "-k", "-S", "-p", "", "--"]
    assert password not in argv
    assert kwargs["input"] == f"{password}\n"
    assert kwargs["start_new_session"] is True


def test_keychain_save_prompts_through_stdin_without_argv_secret(monkeypatch) -> None:
    calls = []

    def fake_prompt(argv, password):
        calls.append((argv, password))
        return True

    monkeypatch.setattr(power, "_answer_keychain_password_prompts", fake_prompt)
    password = "never-in-argv"
    monkeypatch.setattr(power, "_read_keychain_password", lambda: password)

    assert power._save_keychain_password(password) is True
    argv, prompted_password = calls[0]
    assert argv[:4] == ["/usr/bin/script", "-q", "/dev/null", "/usr/bin/security"]
    assert argv[-1] == "-w"
    assert password not in argv
    assert prompted_password == password


def test_keychain_prompt_helper_waits_for_both_prompts() -> None:
    argv = [
        "/bin/sh", "-c",
        "printf 'password data for new item: '; "
        "IFS= read -r first; "
        "printf 'retype password for new item: '; "
        "IFS= read -r second; "
        "[ \"$first\" = \"$second\" ]",
    ]

    assert power._answer_keychain_password_prompts(argv, "two-prompt-secret") is True


def test_keychain_read_keeps_secret_out_of_argv(monkeypatch) -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="saved-secret\n"
        )

    monkeypatch.setattr(power.subprocess, "run", fake_run)

    assert power._read_keychain_password() == "saved-secret"
    argv, kwargs = calls[0]
    assert "saved-secret" not in argv
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.DEVNULL


def test_new_timer_requires_manual_or_saved_password(
    client, monkeypatch, tmp_path,
) -> None:
    deadline_file, starts, _saved = _configure_supported_timer(monkeypatch, tmp_path)

    response = client.post("/api/power/lid-awake", json={"minutes": 15})

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "message": "Enter your Mac password.",
        "password_saved": False,
    }
    assert starts == []
    assert not deadline_file.exists()


def test_saved_password_starts_a_future_timer(client, monkeypatch, tmp_path) -> None:
    _deadline_file, starts, saved = _configure_supported_timer(monkeypatch, tmp_path)
    saved["password"] = "from-keychain"

    response = client.post("/api/power/lid-awake", json={"minutes": 15})

    assert response.status_code == 200
    assert starts == ["from-keychain"]
    assert response.json()["password_saved"] is True


def test_failed_saved_password_is_forgotten(client, monkeypatch, tmp_path) -> None:
    deadline_file, _starts, saved = _configure_supported_timer(monkeypatch, tmp_path)
    saved["password"] = "stale"

    def rejected(*, password: str) -> None:
        raise HTTPException(status_code=409, detail="Password failed.")

    monkeypatch.setattr(power, "_start_privileged_timer", rejected)
    response = client.post("/api/power/lid-awake", json={"minutes": 15})

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "Saved Mac password did not work. Enter a new password.",
        "password_saved": False,
    }
    assert saved["password"] is None
    assert not deadline_file.exists()


def test_active_timer_renews_without_reading_a_password(
    client, monkeypatch, tmp_path,
) -> None:
    deadline_file, starts, _saved = _configure_supported_timer(monkeypatch, tmp_path)
    deadline_file.write_text(f"{int(time.time()) + 600}\n")
    monkeypatch.setattr(
        power, "_read_keychain_password",
        lambda: (_ for _ in ()).throw(AssertionError("password should not be read")),
    )

    response = client.post("/api/power/lid-awake", json={"minutes": 30})

    assert response.status_code == 200
    assert starts == []


def test_forget_saved_password(client, monkeypatch, tmp_path) -> None:
    _deadline_file, _starts, saved = _configure_supported_timer(monkeypatch, tmp_path)
    saved["password"] = "forget-me"

    response = client.delete("/api/power/lid-awake/password")

    assert response.status_code == 200
    assert response.json() == {"password_saved": False}
    assert saved["password"] is None


def test_keychain_save_failure_does_not_hide_a_running_timer(
    client, monkeypatch, tmp_path,
) -> None:
    _deadline_file, starts, saved = _configure_supported_timer(monkeypatch, tmp_path)
    monkeypatch.setattr(power, "_save_keychain_password", lambda _password: False)

    response = client.post(
        "/api/power/lid-awake",
        json={"minutes": 15, "password": "valid-but-not-saved"},
    )

    assert response.status_code == 200
    assert response.json()["active"] is True
    assert response.json()["password_saved"] is False
    assert "could not save" in response.json()["warning"]
    assert starts == ["valid-but-not-saved"]
    assert saved["password"] is None


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
        power._start_privileged_timer(password="wrong")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail == (
            "Password authentication failed. Check your Mac password and try again."
        )
    else:  # pragma: no cover
        raise AssertionError("expected failed authentication to raise HTTPException")
