"""Host-local Jupyter kernel sessions used by Lab notebooks.

Each notebook path owns one long-lived kernel.  The kernel is started with the
exact interpreter and environment selected by the project's runtime config,
so imported libraries and subprocess/CLI calls see the same project runtime.
All ZeroMQ work for a session stays on one worker thread; jupyter-client's
sockets are not moved between FastAPI worker threads.
"""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty
from typing import Any

from jupyter_client import KernelManager

from core.notebook_runtime import RuntimeHandle


class KernelExecutionError(RuntimeError):
    """The local kernel could not start, execute, or respond in time."""

    def __init__(self, detail: str, *, status_code: int = 500) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _session_id(root: Path, rel_path: str) -> str:
    key = f"{root.resolve()}\0{rel_path}".encode("utf-8")
    return "local-" + hashlib.sha1(key).hexdigest()[:12]


def _msg_type(message: dict[str, Any]) -> str:
    return str(message.get("msg_type") or message.get("header", {}).get("msg_type") or "")


def _parent_id(message: dict[str, Any]) -> str:
    return str(message.get("parent_header", {}).get("msg_id") or "")


class _KernelProcess:
    """Blocking kernel operations. Every method runs on one session thread."""

    def __init__(self, handle: RuntimeHandle, session_id: str) -> None:
        self.handle = handle
        self.session_id = session_id
        self.manager: KernelManager | None = None
        self.client: Any = None
        self.kernel_id: str | None = None
        self.interrupt_requested = threading.Event()
        self.busy = threading.Event()

    def start(self, timeout: int = 60) -> None:
        if self.manager is not None:
            return
        manager = KernelManager(kernel_name="python3")
        # A generated kernelspec is unnecessary and would leak global state.
        # Mutating this per-manager in-memory spec gives Jupyter the exact
        # project interpreter while keeping connection-file handling native.
        manager.kernel_spec.argv = [
            self.handle.python,
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ]
        manager.kernel_spec.display_name = self.handle.display_name
        manager.kernel_spec.env = {}
        # Connection files are JSON and jupyter-client decodes the key as
        # UTF-8. Keep the authentication material random but ASCII-safe.
        manager.session.key = secrets.token_hex(32).encode("ascii")
        try:
            manager.start_kernel(
                cwd=self.handle.working_dir,
                env=dict(self.handle.environment),
            )
            client = manager.blocking_client()
            client.start_channels()
            client.wait_for_ready(timeout=timeout)
        except Exception as exc:
            try:
                manager.shutdown_kernel(now=True)
            except Exception:
                pass
            raise KernelExecutionError(f"local Jupyter kernel failed to start: {exc}", status_code=503) from exc
        self.manager = manager
        self.client = client
        provisioner = getattr(manager, "provisioner", None)
        self.kernel_id = str(getattr(provisioner, "kernel_id", "") or self.session_id)

    def execute(self, code: str, timeout: int) -> dict[str, Any]:
        try:
            self.start(timeout=min(timeout, 60))
        except Exception:
            self.interrupt_requested.clear()
            raise
        if self.interrupt_requested.is_set():
            self.interrupt_requested.clear()
            return {
                "output": "",
                "kernel_id": self.kernel_id,
                "execution_count": None,
                "cell_outputs": [{
                    "output_type": "error",
                    "ename": "KeyboardInterrupt",
                    "evalue": "execution interrupted before the kernel became ready",
                    "traceback": ["KeyboardInterrupt: execution interrupted"],
                }],
            }
        assert self.client is not None
        assert self.manager is not None
        client = self.client
        msg_id = client.execute(
            code,
            silent=False,
            store_history=True,
            allow_stdin=False,
            stop_on_error=True,
        )
        outputs: list[dict[str, Any]] = []
        execution_count: int | None = None
        deadline = time.monotonic() + timeout
        idle = False

        try:
            while not idle:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    try:
                        self.manager.interrupt_kernel()
                    except Exception:
                        pass
                    self.interrupt_requested.clear()
                    raise KernelExecutionError(
                        f"local Jupyter execution timed out after {timeout}s",
                        status_code=504,
                    )
                try:
                    message = client.get_iopub_msg(timeout=min(1.0, remaining))
                except Empty:
                    # A cell may be legitimately quiet for minutes while a
                    # library waits on a CLI, database, or subprocess. A
                    # one-second poll miss is not the execution deadline.
                    continue
                if _parent_id(message) != msg_id:
                    continue
                msg_type = _msg_type(message)
                content = message.get("content") or {}
                if msg_type == "status" and content.get("execution_state") == "idle":
                    idle = True
                elif msg_type == "execute_input":
                    value = content.get("execution_count")
                    if isinstance(value, int):
                        execution_count = value
                elif msg_type == "stream":
                    outputs.append({
                        "output_type": "stream",
                        "name": content.get("name", "stdout"),
                        "text": content.get("text", ""),
                    })
                elif msg_type in {"display_data", "execute_result", "update_display_data"}:
                    output_type = "display_data" if msg_type == "update_display_data" else msg_type
                    output: dict[str, Any] = {
                        "output_type": output_type,
                        "data": content.get("data") or {},
                        "metadata": content.get("metadata") or {},
                    }
                    if output_type == "execute_result":
                        output["execution_count"] = content.get("execution_count")
                    if content.get("transient"):
                        output["transient"] = content["transient"]
                    outputs.append(output)
                elif msg_type == "error":
                    outputs.append({
                        "output_type": "error",
                        "ename": content.get("ename", "Error"),
                        "evalue": content.get("evalue", ""),
                        "traceback": content.get("traceback") or [],
                    })
                elif msg_type == "clear_output" and not content.get("wait"):
                    outputs.clear()
        except KernelExecutionError:
            raise
        except Exception as exc:
            self.interrupt_requested.clear()
            raise KernelExecutionError(f"local Jupyter execution failed: {exc}", status_code=502) from exc

        # The shell reply carries the authoritative execution count. Waiting
        # for it also ensures the request has fully completed before another
        # cell is dequeued on this session's single worker.
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                reply = client.get_shell_msg(timeout=min(1.0, remaining))
                if _parent_id(reply) != msg_id:
                    continue
                value = (reply.get("content") or {}).get("execution_count")
                if isinstance(value, int):
                    execution_count = value
                break
        except Empty:
            pass

        self.interrupt_requested.clear()
        return {
            "output": "",
            "kernel_id": self.kernel_id,
            "execution_count": execution_count,
            "cell_outputs": outputs,
        }

    def interrupt(self) -> bool:
        if not self.busy.is_set():
            return False
        self.interrupt_requested.set()
        if self.manager is not None:
            self.manager.interrupt_kernel()
        return True

    def restart(self, timeout: int = 60) -> bool:
        if self.manager is None:
            self.start(timeout=timeout)
            return False
        assert self.client is not None
        self.client.stop_channels()
        self.manager.restart_kernel(now=True)
        self.client = self.manager.blocking_client()
        self.client.start_channels()
        self.client.wait_for_ready(timeout=timeout)
        return True

    def close(self) -> None:
        manager, client = self.manager, self.client
        self.manager = None
        self.client = None
        if client is not None:
            try:
                client.stop_channels()
            except Exception:
                pass
        if manager is not None:
            try:
                manager.shutdown_kernel(now=True)
            except Exception:
                pass
            try:
                manager.cleanup_resources()
            except Exception:
                pass


class _KernelSession:
    def __init__(self, root: Path, rel_path: str, handle: RuntimeHandle) -> None:
        self.root = root.resolve()
        self.rel_path = rel_path
        self.handle = handle
        self.session_id = _session_id(root, rel_path)
        self.executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"lab-kernel-{self.session_id[-6:]}",
        )
        self.process = _KernelProcess(handle, self.session_id)
        self._requests = 0
        self._requests_guard = threading.Lock()

    def begin_request(self) -> None:
        with self._requests_guard:
            self._requests += 1
            self.process.busy.set()

    def end_request(self) -> None:
        with self._requests_guard:
            self._requests = max(0, self._requests - 1)
            if self._requests == 0:
                self.process.busy.clear()

    async def call(self, method: str, *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        fn = getattr(self.process, method)
        return await loop.run_in_executor(self.executor, fn, *args)

    def close_sync(self) -> None:
        # Wake a sleeping cell before queueing shutdown behind it. Without the
        # signal, workspace switching could wait for the cell's full timeout.
        try:
            self.process.interrupt()
        except Exception:
            pass
        try:
            self.executor.submit(self.process.close).result(timeout=15)
        except Exception:
            try:
                self.process.close()
            except Exception:
                pass
            self.executor.shutdown(wait=False, cancel_futures=True)
        else:
            self.executor.shutdown(wait=True, cancel_futures=True)


_sessions: dict[tuple[str, str], _KernelSession] = {}
_sessions_guard = threading.Lock()


def session_name(root: Path, rel_path: str) -> str:
    return _session_id(root, rel_path)


def _session_for(root: Path, rel_path: str, handle: RuntimeHandle) -> _KernelSession:
    key = (str(root.resolve()), rel_path)
    stale: _KernelSession | None = None
    with _sessions_guard:
        session = _sessions.get(key)
        if session is not None and session.handle.fingerprint != handle.fingerprint:
            stale = _sessions.pop(key)
            session = None
        if session is None:
            session = _KernelSession(root, rel_path, handle)
            _sessions[key] = session
    if stale is not None:
        stale.close_sync()
    return session


async def execute(
    root: Path,
    rel_path: str,
    handle: RuntimeHandle,
    code: str,
    timeout: int,
) -> dict[str, Any]:
    session = _session_for(root, rel_path, handle)
    session.begin_request()
    try:
        return await session.call("execute", code, timeout)
    finally:
        session.end_request()


async def restart(root: Path, rel_path: str, handle: RuntimeHandle) -> bool:
    return await _session_for(root, rel_path, handle).call("restart", 60)


async def interrupt(root: Path, rel_path: str, handle: RuntimeHandle) -> bool:
    # Do not enqueue this on the session's single execution worker: that
    # worker is precisely what may be blocked in a long-running cell. Kernel
    # manager interruption sends an OS signal and does not touch the client's
    # ZeroMQ sockets, so it is safe to issue from a helper thread.
    session = _session_for(root, rel_path, handle)
    return await asyncio.to_thread(session.process.interrupt)


def execute_ephemeral(
    handle: RuntimeHandle,
    code: str,
    timeout: int = 120,
) -> dict[str, Any]:
    """Validate a runtime through a real short-lived Jupyter kernel."""
    process = _KernelProcess(handle, "validation")
    try:
        return process.execute(code, timeout)
    finally:
        process.close()


def shutdown_root(root: Path) -> None:
    root_key = str(root.resolve())
    with _sessions_guard:
        matches = [key for key in _sessions if key[0] == root_key]
        sessions = [_sessions.pop(key) for key in matches]
    for session in sessions:
        session.close_sync()


def shutdown_all() -> None:
    with _sessions_guard:
        sessions = list(_sessions.values())
        _sessions.clear()
    for session in sessions:
        session.close_sync()
