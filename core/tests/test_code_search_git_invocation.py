"""Apple launcher resolution retains environment, selection and Git failures."""
import errno
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from core.routes import code_search


@pytest.fixture
def apple_shim(monkeypatch, tmp_path):
    monkeypatch.setattr(code_search.sys, "platform", "darwin")
    monkeypatch.setattr(code_search.shutil, "which", lambda name: "/usr/bin/git")
    executable = tmp_path / "sdk" / "git"
    executable.parent.mkdir()
    executable.write_text("owned fixture")
    executable.chmod(0o700)
    return str(executable)


@pytest.mark.parametrize("platform,selected", [
    ("linux", "/usr/bin/git"), ("darwin", "/opt/homebrew/bin/git"),
    ("darwin", "/owned/custom/git"), ("darwin", None),
])
def test_other_platforms_and_path_selected_git_are_unchanged(monkeypatch, platform, selected):
    monkeypatch.setattr(code_search.sys, "platform", platform)
    monkeypatch.setattr(code_search.shutil, "which", lambda name: selected)
    monkeypatch.setattr(code_search.subprocess, "run", lambda *a, **k: pytest.fail("unexpected discovery"))
    assert code_search._git_invocation() is None


def test_resolution_keeps_entire_launcher_environment(monkeypatch, apple_shim):
    calls = []
    before = dict(os.environ)

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args == ["/usr/bin/xcrun", "--find", "git"]:
            return SimpleNamespace(returncode=0, stdout=apple_shim + "\n")
        assert args == ["/usr/bin/xcrun", "/usr/bin/env", "-0"]
        return SimpleNamespace(returncode=0, stdout=b"PATH=/custom\0SDKROOT=/sdk\0VALUE=a=b\nnext\0ODD=\xff\0")

    monkeypatch.setattr(code_search.subprocess, "run", run)
    executable, environment = code_search._git_invocation()
    assert executable == apple_shim
    assert environment == {"PATH": "/custom", "SDKROOT": "/sdk", "VALUE": "a=b\nnext", "ODD": os.fsdecode(b"\xff")}
    changed_names = sorted(key for key in before.keys() | os.environ.keys()
                           if before.get(key) != os.environ.get(key))
    assert not changed_names, changed_names
    assert len(calls) == 2 and all(kwargs["timeout"] == 1 for _, kwargs in calls)
    assert all(kwargs["capture_output"] for _, kwargs in calls)


@pytest.mark.parametrize("kind", ["failure", "relative", "missing", "not-executable", "shim", "timeout", "oserror", "decode"])
def test_lookup_failure_falls_back(monkeypatch, apple_shim, kind):
    def run(args, **kwargs):
        assert args == ["/usr/bin/xcrun", "--find", "git"]
        if kind == "timeout":
            raise subprocess.TimeoutExpired(args, 1)
        if kind == "oserror":
            raise FileNotFoundError()
        if kind == "decode":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
        if kind == "not-executable":
            Path(apple_shim).chmod(0o600)
        value = {"relative": "sdk/git", "missing": apple_shim + ".missing", "shim": "/usr/bin/git"}.get(kind, apple_shim)
        return SimpleNamespace(returncode=int(kind == "failure"), stdout=value)

    monkeypatch.setattr(code_search.subprocess, "run", run)
    assert code_search._git_invocation() is None


@pytest.mark.parametrize("data,status", [(b"PATH=x", 0), (b"invalid\0", 0), (b"=value\0", 0), (b"PATH=x\0", 1)])
def test_invalid_environment_falls_back(monkeypatch, apple_shim, data, status):
    def run(args, **kwargs):
        return (SimpleNamespace(returncode=0, stdout=apple_shim) if "--find" in args
                else SimpleNamespace(returncode=status, stdout=data))
    monkeypatch.setattr(code_search.subprocess, "run", run)
    assert code_search._git_invocation() is None


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("env", 1)])
def test_environment_discovery_failure_falls_back(monkeypatch, apple_shim, error):
    def run(args, **kwargs):
        if "--find" in args:
            return SimpleNamespace(returncode=0, stdout=apple_shim)
        raise error
    monkeypatch.setattr(code_search.subprocess, "run", run)
    assert code_search._git_invocation() is None


@pytest.mark.parametrize("outcome", ["ok", "missing", "permission", "exec-format", "timeout", "exit"])
def test_git_uses_context_and_preserves_failure_handling(monkeypatch, outcome):
    calls = []
    invocation = ("/selected/git", {"SDKROOT": "/selected/sdk"})

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == invocation[0]:
            if outcome == "missing":
                raise FileNotFoundError()
            if outcome == "permission":
                raise PermissionError()
            if outcome == "exec-format":
                raise OSError(errno.ENOEXEC, "tool replaced during selection")
            if outcome == "timeout":
                raise subprocess.TimeoutExpired(args, 3)
        return SimpleNamespace(returncode=7 if outcome == "exit" else 0, stdout="result\n", stderr="stderr")

    monkeypatch.setattr(code_search.subprocess, "run", run)
    result = code_search._git(Path("/owned"), ["rev-parse", "HEAD"], timeout=3, invocation=invocation)
    assert calls[0][0] == ["/selected/git", "-C", "/owned", "rev-parse", "HEAD"]
    assert calls[0][1]["env"] is invocation[1]
    assert all(kwargs["timeout"] == 3 for _, kwargs in calls)
    if outcome in ("missing", "permission", "exec-format"):
        assert len(calls) == 2 and calls[1][0][0] == "git" and calls[1][1]["env"] is None
    else:
        assert len(calls) == 1
    assert result == ((124, "", "git timed out after 3s") if outcome == "timeout"
                      else (7 if outcome == "exit" else 0, "result\n", "stderr"))


@pytest.mark.parametrize("error", [FileNotFoundError(), PermissionError()])
def test_normal_git_errors_keep_original_behavior(monkeypatch, error):
    def denied(*args, **kwargs):
        raise error
    monkeypatch.setattr(code_search.subprocess, "run", denied)
    if isinstance(error, PermissionError):
        with pytest.raises(PermissionError):
            code_search._git(Path("/owned"), ["rev-parse", "HEAD"])
    else:
        assert code_search._git(Path("/owned"), ["rev-parse", "HEAD"]) == (
            127, "", "git executable not found",
        )


@pytest.mark.skipif(sys.platform != "darwin" or shutil.which("git") != "/usr/bin/git", reason="Apple Git launcher only")
@pytest.mark.parametrize("extra", [{}, {"CPATH": "/owned/include", "LIBRARY_PATH": "/owned/lib", "MANPATH": "/owned/man"}])
def test_native_wrapper_and_resolved_git_inherit_equal_environment(tmp_path, monkeypatch, extra):
    # Only differing names appear on failure; never print inherited values.
    for key, value in extra.items():
        monkeypatch.setenv(key, value)
    subprocess.run(["git", "-C", str(tmp_path), "init", "--quiet"], check=True)
    invocation = code_search._git_invocation()
    assert invocation is not None

    def inherited(executable, env):
        raw = subprocess.check_output([
            executable, "-C", str(tmp_path), "-c", "alias.fixture-env=!env -0", "fixture-env",
        ], env=env)
        return dict(part.split(b"=", 1) for part in raw.split(b"\0") if b"=" in part)

    original = inherited("git", None)
    resolved = inherited(*invocation)
    differences = sorted(os.fsdecode(key) for key in original.keys() | resolved.keys()
                         if original.get(key) != resolved.get(key))
    assert not differences, differences
