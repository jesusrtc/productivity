"""Exercise draft state and line marks without a browser or client documents."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_note_editor_drafts_and_line_marks():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required')
    script = Path(__file__).with_suffix('.mjs')
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
