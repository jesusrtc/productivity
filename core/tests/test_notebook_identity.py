"""Notebook session metadata must stay cheap and agree with execution identity."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_session_metadata_does_not_import_kernel_execution(tmp_path):
    # Use a new interpreter: the surrounding test suite may already have
    # imported Jupyter to run kernels, which would conceal the cold dependency.
    code = r'''
import json,sys
from pathlib import Path
from fastapi import HTTPException
from core.routes import nb_exec
sys.modules['core.notebook_kernel'] = None
sys.modules['jupyter_client'] = None
root=Path(sys.argv[1])
nb_exec.auth.request_root=lambda request:root
result=nb_exec.session_for('workspaces/demo/notebooks/review.ipynb',object())
errors=[]
for path in ['/outside.ipynb','../outside.ipynb','notes/readme.md']:
    try:nb_exec.session_for(path,object())
    except HTTPException as exc:errors.append(exc.status_code)
print(json.dumps({'result':result,'errors':errors}))
'''
    env = {key: value for key, value in os.environ.items() if key not in ('LAB_VAULT', 'LAB_WORKSPACE')}
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    rel = 'workspaces/demo/notebooks/review.ipynb'
    expected = 'local-' + hashlib.sha1(f'{tmp_path.resolve()}\0{rel}'.encode()).hexdigest()[:12]
    assert body == {'result': {'path': rel, 'session': expected, 'provider': 'local',
                              'capabilities': ['execute', 'restart', 'interrupt']},
                    'errors': [400, 400, 400]}


@pytest.mark.parametrize('directory', ['workspaces', 'projects'])
def test_session_identity_matches_kernel_and_survives_workspace_folder_move(tmp_path, monkeypatch, directory):
    from core.notebook_identity import notebook_identity, session_name
    from core import notebook_kernel
    from lab import workspace_identity

    (tmp_path / directory).mkdir()
    # The stable metadata ID may differ from both old and renamed folders.
    # The real metadata reader has separate coverage; record each lookup here
    # to ensure no path/ID cache hides later changes.
    lookups = []
    stable_id = ['stable-id']
    def identity(folder):
        lookups.append(folder)
        return stable_id[0]
    monkeypatch.setattr(workspace_identity, 'id_at', identity)
    old = f'{directory}/original/notebooks/a.ipynb'
    moved = f'{directory}/renamed/notebooks/a.ipynb'
    expected_path = f'{directory}/stable-id/notebooks/a.ipynb'
    expected_id = 'local-' + hashlib.sha1(f'{tmp_path.resolve()}\0{expected_path}'.encode()).hexdigest()[:12]
    assert notebook_identity(tmp_path, old) == expected_path
    assert session_name(tmp_path, old) == session_name(tmp_path, moved) == expected_id
    assert notebook_kernel.session_name(tmp_path, moved) == expected_id
    assert notebook_kernel._session_id(tmp_path, moved) == expected_id
    assert notebook_kernel._notebook_identity(tmp_path, moved) == expected_path
    assert session_name(tmp_path, moved.replace('a.ipynb', 'b.ipynb')) != expected_id
    stable_id[0] = 'changed-id'
    assert session_name(tmp_path, moved) != expected_id
    assert tmp_path / directory / 'renamed' in lookups
    outside = 'notes/a.ipynb'
    before = len(lookups)
    assert notebook_identity(tmp_path, outside) == outside
    assert len(lookups) == before
    assert session_name(tmp_path / 'another-vault', outside) != session_name(tmp_path, outside)


def test_session_identity_resolves_vault_alias_but_retains_relative_notebook_identity(tmp_path):
    from core.notebook_identity import session_name
    root = tmp_path / 'vault'
    root.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(root, target_is_directory=True)
    assert session_name(root, 'notes/a.ipynb') == session_name(alias, 'notes/a.ipynb')
