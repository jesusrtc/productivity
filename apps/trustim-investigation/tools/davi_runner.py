#!/usr/bin/env python3
"""
DAVI Runner — Execute DAVI widgets on Darwin via darwin-local-client.

Usage:
    davi_runner.py setup              Set up darwin-local-client (one-time)
    davi_runner.py start              Start session (proxy + kernel + Darwin)
    davi_runner.py run <code>         Execute Python code on Darwin
    davi_runner.py run-local <code>   Execute code on the local kernel
    davi_runner.py stop               Stop session
    davi_runner.py status             Check session status

Options for run/run-local:
    --timeout N          Execution timeout in seconds (default: 600)
    --notebook NAME      Save code + output to notebooks/<NAME>.ipynb

All output (except setup) is JSON on stdout. Progress messages go to stderr.
Notebooks are saved to the notebooks/ directory in the repo root.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path("/tmp/davi-runner")
DLC_DIR = Path("/tmp/lipy-darwin-local-client")
DLC_VENV = DLC_DIR / ".venv"
DLC_PYTHON = str(DLC_VENV / "bin" / "python")

# Notebook audit trail directory (override with DAVI_NOTEBOOKS_DIR env var)
REPO_ROOT = Path(__file__).parent.parent.resolve()
NOTEBOOKS_DIR = Path(os.environ["DAVI_NOTEBOOKS_DIR"]) if "DAVI_NOTEBOOKS_DIR" in os.environ else REPO_ROOT / "notebooks"


def _json_out(data):
    print(json.dumps(data, indent=2))


def _ensure_dlc_python():
    """Re-exec with DLC venv Python so jupyter_client and DLC extension are importable."""
    if not Path(DLC_PYTHON).exists():
        _json_out({"success": False, "error": "Run 'davi_runner.py setup' first"})
        sys.exit(1)
    if os.path.realpath(sys.executable) != os.path.realpath(DLC_PYTHON):
        os.execv(DLC_PYTHON, [DLC_PYTHON, os.path.abspath(__file__)] + sys.argv[1:])


# ---------------------------------------------------------------------------
# Kernel execution helper
# ---------------------------------------------------------------------------

def _execute_on_kernel(kc, code, timeout=120):
    """Execute code on a kernel via BlockingKernelClient, return structured output."""
    import queue

    msg_id = kc.execute(code)
    stdout, stderr, displays = [], [], []
    result, error = None, None

    while True:
        try:
            msg = kc.get_iopub_msg(timeout=timeout)
        except queue.Empty:
            if error is None:
                error = f"Timeout after {timeout}s"
            break

        if msg["parent_header"].get("msg_id") != msg_id:
            continue

        mt = msg["msg_type"]
        c = msg["content"]

        if mt == "stream":
            (stdout if c["name"] == "stdout" else stderr).append(c["text"])
        elif mt == "execute_result":
            result = c["data"].get("text/plain")
        elif mt == "display_data":
            data = c.get("data", {})
            if "text/html" in data:
                displays.append({"type": "html", "data": data["text/html"]})
            elif "image/png" in data:
                displays.append({"type": "png", "data": "(binary png)"})
            elif "text/plain" in data:
                displays.append({"type": "text", "data": data["text/plain"]})
        elif mt == "error":
            error = "\n".join(c.get("traceback", []))
        elif mt == "status" and c["execution_state"] == "idle":
            break

    stderr_text = "".join(stderr)
    # Remote kernel errors from %%remote come through as stderr
    if error is None and "Remote kernel error:" in stderr_text:
        error = stderr_text

    return {
        "success": error is None,
        "stdout": "".join(stdout),
        "stderr": stderr_text,
        "result": result,
        "displays": displays,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Notebook audit trail
# ---------------------------------------------------------------------------

def _append_to_notebook(nb_name, code, output):
    """Append a code cell with outputs to a local .ipynb notebook."""
    import nbformat
    from datetime import datetime

    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    nb_path = NOTEBOOKS_DIR / f"{nb_name}.ipynb"

    if nb_path.exists():
        nb = nbformat.read(str(nb_path), as_version=4)
    else:
        nb = nbformat.v4.new_notebook()
        nb.metadata["kernelspec"] = {
            "display_name": "DAVI Runner (Darwin)",
            "language": "python",
            "name": "davi-runner",
        }
        # Add a header cell
        header = nbformat.v4.new_markdown_cell(
            f"# Investigation: {nb_name}\n\n"
            f"Auto-generated audit trail via `davi_runner.py`.\n\n"
            f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        nb.cells.append(header)

    # Build notebook outputs from our JSON output
    cell_outputs = []

    if output.get("stdout"):
        cell_outputs.append(nbformat.v4.new_output(
            output_type="stream", name="stdout", text=output["stdout"],
        ))

    if output.get("stderr") and not output.get("error"):
        cell_outputs.append(nbformat.v4.new_output(
            output_type="stream", name="stderr", text=output["stderr"],
        ))

    for d in output.get("displays", []):
        if d["type"] == "html":
            cell_outputs.append(nbformat.v4.new_output(
                output_type="display_data",
                data={"text/html": d["data"]},
                metadata={},
            ))
        elif d["type"] == "text":
            cell_outputs.append(nbformat.v4.new_output(
                output_type="display_data",
                data={"text/plain": d["data"]},
                metadata={},
            ))

    if output.get("result"):
        cell_outputs.append(nbformat.v4.new_output(
            output_type="execute_result",
            data={"text/plain": output["result"]},
            metadata={},
            execution_count=len([c for c in nb.cells if c.cell_type == "code"]) + 1,
        ))

    if output.get("error"):
        cell_outputs.append(nbformat.v4.new_output(
            output_type="error",
            ename="Error",
            evalue=output["error"][:200],
            traceback=output["error"].split("\n"),
        ))

    # Add timestamp as a comment at the top of the cell
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cell_source = f"# [{timestamp}]\n{code}"

    cell = nbformat.v4.new_code_cell(source=cell_source)
    cell.outputs = cell_outputs
    nb.cells.append(cell)

    nbformat.write(nb, str(nb_path))
    return str(nb_path)


# ---------------------------------------------------------------------------
# PID helpers
# ---------------------------------------------------------------------------

def _save_pid(name, pid):
    (STATE_DIR / f"{name}.pid").write_text(str(pid))


def _is_alive(name):
    pf = STATE_DIR / f"{name}.pid"
    if not pf.exists():
        return False
    try:
        os.kill(int(pf.read_text().strip()), 0)
        return True
    except (ProcessLookupError, ValueError, PermissionError):
        return False


def _kill(name):
    pf = STATE_DIR / f"{name}.pid"
    if pf.exists():
        try:
            os.kill(int(pf.read_text().strip()), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
        pf.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _find_python():
    """Find Python >=3.10 for the venv."""
    for name in ["python3.13", "python3.12", "python3.11", "python3.10"]:
        path = subprocess.run(["which", name], capture_output=True, text=True)
        if path.returncode == 0:
            return path.stdout.strip()
    # Check common brew/system locations
    for p in [
        "/usr/local/bin/python3.12", "/opt/homebrew/bin/python3.12",
        "/usr/local/bin/python3.11", "/opt/homebrew/bin/python3.11",
        "/usr/local/bin/python3.10", "/opt/homebrew/bin/python3.10",
    ]:
        if os.path.exists(p):
            return p
    return None


# Dependencies from pyproject.toml (avoids needing lipy-hatch-version build plugin)
DLC_DEPS = [
    "aiohttp>=3.9.0", "requests>=2.32.0", "urllib3>=2.6.0",
    "websocket-client>=1.9.0", "ipython>=8.0.0", "ipykernel>=6.0.0",
    "jupyter_client>=8.0.0", "nbformat>=5.0.0",
]


def cmd_setup():
    """Clone darwin-local-client, create venv, install deps. Runs with system Python."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not DLC_DIR.exists():
        print("Cloning lipy-darwin-local-client...", file=sys.stderr)
        subprocess.run(
            ["git", "clone", "git@github.com:linkedin-multiproduct/lipy-darwin-local-client.git", str(DLC_DIR)],
            check=True,
        )

    py = _find_python()
    if py is None:
        _json_out({"success": False, "error": "Python >=3.10 not found. Install via: brew install python@3.12"})
        return

    if not DLC_VENV.exists():
        print(f"Creating venv with {py}...", file=sys.stderr)
        subprocess.run([py, "-m", "venv", str(DLC_VENV)], check=True)

    print("Upgrading pip...", file=sys.stderr)
    subprocess.run([DLC_PYTHON, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)

    # Install deps directly (skips lipy-hatch-version build plugin requirement)
    print("Installing dependencies...", file=sys.stderr)
    subprocess.run([DLC_PYTHON, "-m", "pip", "install", "-q"] + DLC_DEPS, check=True)

    # Add DLC source to the venv via .pth file so it's importable
    site_pkgs = subprocess.run(
        [DLC_PYTHON, "-c", "import site; print(site.getsitepackages()[0])"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    pth_file = Path(site_pkgs) / "darwin-local-client.pth"
    pth_file.write_text(str(DLC_DIR / "src") + "\n")
    print(f"Linked DLC source via {pth_file}", file=sys.stderr)

    # Register a kernel spec pointing to the DLC venv Python
    print("Registering ipykernel...", file=sys.stderr)
    subprocess.run(
        [DLC_PYTHON, "-m", "ipykernel", "install", "--user",
         "--name=davi-runner", "--display-name=DAVI Runner"],
        check=True,
    )

    _json_out({"success": True, "message": "Setup complete", "python": py})


def cmd_start():
    """Start proxy + kernel, load extension, connect to Darwin."""
    _ensure_dlc_python()
    import jupyter_client

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Already running?
    if _is_alive("kernel") and _is_alive("proxy"):
        _json_out({"success": True, "message": "Session already active", "already_running": True})
        return

    # Clean up stale processes
    _kill("proxy")
    _kill("kernel")

    # 1. Start proxy (bridges localhost:8889 → Darwin)
    print("Starting jupyter-proxy...", file=sys.stderr)
    proxy = subprocess.Popen(
        [DLC_PYTHON, "-m", "linkedin.darwinlocalclient.client_server_application.jupyter_server"],
        stdout=open(STATE_DIR / "proxy.log", "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _save_pid("proxy", proxy.pid)
    time.sleep(3)

    if proxy.poll() is not None:
        log = (STATE_DIR / "proxy.log").read_text()
        _json_out({"success": False, "error": f"Proxy exited immediately. Log:\n{log}"})
        return

    # 2. Start kernel as a detached process (survives after this script exits)
    print("Starting kernel...", file=sys.stderr)
    conn_file = STATE_DIR / "kernel-connection.json"

    # Write connection file manually (KernelManager deletes it on GC)
    import uuid
    from jupyter_client import find_connection_file
    from jupyter_client.connect import ConnectionFileMixin

    cfm = ConnectionFileMixin()
    cfm.connection_file = str(conn_file)
    cfm.write_connection_file()
    # Detach so GC doesn't clean up
    cfm.connection_file = ""

    # Launch ipykernel as a fully detached process
    kernel_proc = subprocess.Popen(
        [DLC_PYTHON, "-m", "ipykernel_launcher", "-f", str(conn_file)],
        stdout=open(STATE_DIR / "kernel.log", "w"),
        stderr=subprocess.STDOUT,
        cwd=str(DLC_DIR),
        start_new_session=True,
    )
    _save_pid("kernel", kernel_proc.pid)
    time.sleep(2)

    if kernel_proc.poll() is not None:
        log = (STATE_DIR / "kernel.log").read_text()
        _json_out({"success": False, "error": f"Kernel exited immediately. Log:\n{log}"})
        return

    # 3. Connect to kernel and set up Darwin
    kc = jupyter_client.BlockingKernelClient()
    kc.load_connection_file(str(conn_file))
    kc.start_channels()
    kc.wait_for_ready(timeout=30)

    # Load DLC extension
    r = _execute_on_kernel(kc, "%load_ext linkedin.darwinlocalclient.kernel_magic")
    if not r["success"]:
        kc.stop_channels()
        _json_out({"success": False, "error": f"Failed to load extension: {r['error']}", "stderr": r["stderr"]})
        return

    # Connect to Darwin (pod startup can take up to 150s)
    print("Connecting to Darwin (may take up to 150s for pod startup)...", file=sys.stderr)
    r = _execute_on_kernel(kc, "%remote --connect --new", timeout=180)
    kc.stop_channels()

    if r["success"]:
        r["message"] = "Connected to Darwin"
    _json_out(r)


def cmd_run(code, local=False, timeout=600, notebook=None):
    """Execute code on Darwin (or locally if local=True)."""
    _ensure_dlc_python()
    import jupyter_client

    conn_path = STATE_DIR / "kernel-connection.json"
    if not conn_path.exists():
        _json_out({"success": False, "error": "No active session. Run 'start' first."})
        return

    kc = jupyter_client.BlockingKernelClient()
    kc.load_connection_file(str(conn_path))
    kc.start_channels()

    try:
        full_code = code if local else f"%%remote\n{code}"
        r = _execute_on_kernel(kc, full_code, timeout=timeout)

        # Save to notebook audit trail
        if notebook:
            nb_path = _append_to_notebook(notebook, code, r)
            r["notebook"] = nb_path

        _json_out(r)
    finally:
        kc.stop_channels()


def cmd_stop():
    """Gracefully disconnect from Darwin, stop kernel and proxy."""
    _ensure_dlc_python()

    conn_path = STATE_DIR / "kernel-connection.json"
    if conn_path.exists():
        try:
            import jupyter_client

            kc = jupyter_client.BlockingKernelClient()
            kc.load_connection_file(str(conn_path))
            kc.start_channels()
            _execute_on_kernel(kc, "%remote --shutdown", timeout=10)
            kc.stop_channels()
        except Exception:
            pass
        conn_path.unlink(missing_ok=True)

    _kill("kernel")
    _kill("proxy")

    _json_out({"success": True, "message": "Session stopped"})


def cmd_status():
    """Check if session components are alive."""
    kernel = _is_alive("kernel")
    proxy = _is_alive("proxy")
    conn = (STATE_DIR / "kernel-connection.json").exists()
    _json_out({
        "session_active": kernel and proxy and conn,
        "kernel_alive": kernel,
        "proxy_alive": proxy,
        "has_connection_file": conn,
    })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "setup":
        cmd_setup()
    elif cmd == "start":
        cmd_start()
    elif cmd == "run":
        if len(sys.argv) < 3:
            _json_out({"success": False, "error": "Usage: davi_runner.py run <code> [--timeout N] [--notebook NAME]"})
            sys.exit(1)
        timeout = 600
        notebook = None
        if "--timeout" in sys.argv:
            idx = sys.argv.index("--timeout")
            timeout = int(sys.argv[idx + 1])
        if "--notebook" in sys.argv:
            idx = sys.argv.index("--notebook")
            notebook = sys.argv[idx + 1]
        cmd_run(sys.argv[2], timeout=timeout, notebook=notebook)
    elif cmd == "run-local":
        if len(sys.argv) < 3:
            _json_out({"success": False, "error": "Usage: davi_runner.py run-local <code> [--notebook NAME]"})
            sys.exit(1)
        notebook = None
        if "--notebook" in sys.argv:
            idx = sys.argv.index("--notebook")
            notebook = sys.argv[idx + 1]
        cmd_run(sys.argv[2], local=True, notebook=notebook)
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "status":
        cmd_status()
    else:
        _json_out({"success": False, "error": f"Unknown command: {cmd}"})
        sys.exit(1)
