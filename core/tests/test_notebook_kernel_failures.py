from queue import Empty
from types import SimpleNamespace
import sys

import pytest

from core import notebook_kernel as kernels
from core.notebook_runtime import RuntimeHandle


@pytest.fixture
def handle(tmp_path):
    return RuntimeHandle(workspace_id="demo", python=sys.executable,
                         working_dir=str(tmp_path), environment={},
                         fingerprint="test", display_name="Test")


class FakeClient:
    def __init__(self):
        self.stopped = False

    def start_channels(self):
        self.stopped = False

    def stop_channels(self):
        self.stopped = True

    def wait_for_ready(self, timeout):
        pass

    def execute(self, *args, **kwargs):
        return "run"

    def get_iopub_msg(self, timeout):
        raise Empty()


class FakeManager:
    def __init__(self):
        self.kernel_spec = SimpleNamespace()
        self.session = SimpleNamespace()
        self.client = FakeClient()
        self.cleaned = self.stopped = self.interrupted = False
        self.alive = True

    def start_kernel(self, **kwargs):
        pass

    def blocking_client(self):
        return self.client

    def shutdown_kernel(self, **kwargs):
        self.stopped = True

    def cleanup_resources(self):
        self.cleaned = True

    def is_alive(self):
        return self.alive

    def interrupt_kernel(self):
        self.interrupted = True

    def restart_kernel(self, **kwargs):
        pass


@pytest.mark.parametrize("phase", ["start", "ready", "restart"])
def test_failed_startup_closes_channels_and_manager_resources(handle, monkeypatch, phase):
    manager = FakeManager()
    monkeypatch.setattr(kernels, "KernelManager", lambda **kwargs: manager)
    process = kernels._KernelProcess(handle, "test")

    def fail(*args, **kwargs):
        raise OSError("failed startup")

    if phase == "restart":
        process.start()
    monkeypatch.setattr(manager if phase == "start" else manager.client,
                        "start_kernel" if phase == "start" else "wait_for_ready", fail)
    with pytest.raises(kernels.KernelExecutionError) as error:
        process.restart() if phase == "restart" else process.start()
    assert error.value.status_code == 503
    assert manager.stopped and manager.cleaned
    if phase != "start":
        assert manager.client.stopped
    assert process.manager is None and process.client is None


def test_dead_kernel_fails_without_waiting_for_execution_deadline(handle, monkeypatch):
    manager = FakeManager()
    manager.alive = False
    monkeypatch.setattr(kernels, "KernelManager", lambda **kwargs: manager)
    process = kernels._KernelProcess(handle, "test")
    with pytest.raises(kernels.KernelExecutionError, match="exited during execution") as error:
        process.execute("pass", 1800)
    assert error.value.status_code == 502
    assert manager.client.stopped and manager.cleaned


@pytest.mark.parametrize("responds", [True, False])
def test_timeout_only_reuses_a_kernel_that_acknowledged_interrupt(handle, monkeypatch, responds):
    manager = FakeManager()
    monkeypatch.setattr(kernels, "KernelManager", lambda **kwargs: manager)
    # Fast-forward the bounded drain without sleeping in a unit test.
    ticks = iter(range(100))
    monkeypatch.setattr(kernels.time, "monotonic", lambda: next(ticks))
    if responds:
        monkeypatch.setattr(manager.client, "get_iopub_msg", lambda **kwargs: {
            "msg_type": "status", "parent_header": {"msg_id": "run"},
            "content": {"execution_state": "idle"},
        })
    process = kernels._KernelProcess(handle, "test")
    with pytest.raises(kernels.KernelExecutionError, match="timed out") as error:
        process.execute("pass", 0)
    assert error.value.status_code == 504
    assert manager.interrupted
    assert (process.manager is manager) == responds
    assert manager.cleaned == (not responds)
    process.close()
