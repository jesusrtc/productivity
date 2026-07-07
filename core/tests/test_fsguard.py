"""Unit tests for core.fsguard: the 503-on-stall guard around blocking
filesystem calls against a (possibly wedged) workspace volume."""
from __future__ import annotations

import errno
import logging
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from core import fsguard


@pytest.fixture(autouse=True)
def _reset_inflight():
    """Guard against cross-test leakage of the module-level inflight counter."""
    fsguard._inflight = 0
    yield
    fsguard._inflight = 0


# ─── workspace_name() ───────────────────────────────────────────────────────


def test_workspace_name_matches_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws_dir = tmp_path / "workspaces" / "productivity"
    ws_dir.mkdir(parents=True)
    lab_home = tmp_path / ".lab-home"
    lab_home.mkdir()
    (lab_home / "workspaces.toml").write_text(
        'active = "ssd"\n\n'
        "[[workspaces]]\n"
        'id = "ssd"\n'
        'name = "ssd"\n'
        f'path = "{ws_dir}"\n'
    )
    monkeypatch.setenv("LAB_HOME", str(lab_home))

    assert fsguard.workspace_name(ws_dir) == "ssd"


def test_workspace_name_registry_read_fresh_each_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry ids/names can be renamed while the server runs; workspace_name
    must reflect the current file, not a cached value."""
    ws_dir = tmp_path / "workspaces" / "productivity"
    ws_dir.mkdir(parents=True)
    lab_home = tmp_path / ".lab-home"
    lab_home.mkdir()
    registry = lab_home / "workspaces.toml"
    registry.write_text(
        "[[workspaces]]\n"
        'id = "old-id"\n'
        'name = "old-name"\n'
        f'path = "{ws_dir}"\n'
    )
    monkeypatch.setenv("LAB_HOME", str(lab_home))

    assert fsguard.workspace_name(ws_dir) == "old-name"

    registry.write_text(
        "[[workspaces]]\n"
        'id = "ssd"\n'
        'name = "ssd"\n'
        f'path = "{ws_dir}"\n'
    )
    assert fsguard.workspace_name(ws_dir) == "ssd"


def test_workspace_name_falls_back_to_lab_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws_dir = tmp_path / "workspaces" / "myws"
    ws_dir.mkdir(parents=True)
    (ws_dir / "lab.toml").write_text('[workspace]\nname = "My Workspace"\n')
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home-empty"))

    assert fsguard.workspace_name(ws_dir) == "My Workspace"


def test_workspace_name_falls_back_to_dir_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws_dir = tmp_path / "workspaces" / "bare"
    ws_dir.mkdir(parents=True)
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home-empty"))

    assert fsguard.workspace_name(ws_dir) == "bare"


# ─── guarded() ──────────────────────────────────────────────────────────────


def test_guarded_fast_op_passes_through(tmp_path: Path) -> None:
    assert fsguard.guarded(tmp_path, lambda x, y: x + y, 20, 22) == 42


def test_guarded_timeout_raises_503_with_exact_detail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home-empty"))
    started = time.monotonic()
    with pytest.raises(HTTPException) as exc_info:
        fsguard.guarded(tmp_path, time.sleep, 0.3, timeout=0.05)
    elapsed = time.monotonic() - started

    assert exc_info.value.status_code == 503
    expected_name = fsguard.workspace_name(tmp_path)
    assert exc_info.value.detail == f"resource is not available for workspace {expected_name}"
    # Should fail fast at the timeout, not wait for the full blocking call.
    assert elapsed < 0.25


def test_guarded_eintr_oserror_mapped_to_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home-empty"))

    def _stalled(*_args):
        raise OSError(errno.EINTR, "interrupted system call")

    with pytest.raises(HTTPException) as exc_info:
        fsguard.guarded(tmp_path, _stalled)

    assert exc_info.value.status_code == 503
    expected_name = fsguard.workspace_name(tmp_path)
    assert exc_info.value.detail == f"resource is not available for workspace {expected_name}"


def test_guarded_bare_interrupted_error_mapped_to_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home-empty"))

    def _stalled(*_args):
        raise InterruptedError()

    with pytest.raises(HTTPException) as exc_info:
        fsguard.guarded(tmp_path, _stalled)

    assert exc_info.value.status_code == 503


def test_guarded_unrelated_oserror_propagates(tmp_path: Path) -> None:
    """A non-EINTR OSError (e.g. a genuinely missing file) is a real error,
    not a stall -- it should propagate unchanged, not turn into a 503."""

    def _missing(*_args):
        raise OSError(errno.ENOENT, "no such file or directory")

    with pytest.raises(OSError) as exc_info:
        fsguard.guarded(tmp_path, _missing)

    assert exc_info.value.errno == errno.ENOENT


def test_guarded_other_exceptions_propagate(tmp_path: Path) -> None:
    def _boom(*_args):
        raise ValueError("not a filesystem problem")

    with pytest.raises(ValueError):
        fsguard.guarded(tmp_path, _boom)


def test_guarded_saturated_pool_fails_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home-empty"))
    # Whitebox: simulate every worker slot already occupied by a stuck call
    # rather than actually spinning up _MAX_WORKERS blocking threads (which
    # would make this test slow/racy). guarded() must refuse to even submit
    # a new task once the pool looks saturated.
    fsguard._inflight = fsguard._MAX_WORKERS
    started = time.monotonic()
    with pytest.raises(HTTPException) as exc_info:
        fsguard.guarded(tmp_path, lambda: "unreachable")
    elapsed = time.monotonic() - started

    assert exc_info.value.status_code == 503
    expected_name = fsguard.workspace_name(tmp_path)
    assert exc_info.value.detail == f"resource is not available for workspace {expected_name}"
    assert elapsed < 0.05


def test_guarded_timeout_logs_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A stall must land an ERROR-level log entry (routed to errors.log by
    the server's levelno filter), not just the 503 to the caller."""
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home-empty"))
    expected_name = fsguard.workspace_name(tmp_path)
    with caplog.at_level(logging.ERROR, logger="core.fsguard"):
        with pytest.raises(HTTPException):
            fsguard.guarded(tmp_path, time.sleep, 0.3, timeout=0.05)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.ERROR
    msg = record.getMessage()
    assert "timeout" in msg
    assert "0.05" in msg
    assert expected_name in msg


def test_guarded_eintr_logs_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home-empty"))
    expected_name = fsguard.workspace_name(tmp_path)

    def _stalled(*_args):
        raise OSError(errno.EINTR, "interrupted system call")

    with caplog.at_level(logging.ERROR, logger="core.fsguard"):
        with pytest.raises(HTTPException):
            fsguard.guarded(tmp_path, _stalled)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.ERROR
    msg = record.getMessage()
    assert "EINTR" in msg
    assert expected_name in msg


def test_guarded_fast_op_does_not_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="core.fsguard"):
        assert fsguard.guarded(tmp_path, lambda: "ok") == "ok"
    assert len(caplog.records) == 0


def test_guarded_env_timeout_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home-empty"))
    monkeypatch.setenv("LAB_FS_TIMEOUT_SECONDS", "0.05")
    started = time.monotonic()
    with pytest.raises(HTTPException) as exc_info:
        fsguard.guarded(tmp_path, time.sleep, 0.3)
    elapsed = time.monotonic() - started

    assert exc_info.value.status_code == 503
    assert elapsed < 0.25
