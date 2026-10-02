"""Run native Objective clicks against the explicitly selected staging workspace.

Uses the real server, normal polling, real registered large worktrees, and a
fresh Chrome profile. No input is sent to terminals. Authentication stays in
the subprocess environment and is never printed or committed.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

from core import auth
from lab import paths

checkout = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--workspace', default='large-projects')
parser.add_argument('--output', default='/private/tmp/objectives-staging-latency.json')
args = parser.parse_args()
root = paths.find_vault_root()
workspace = paths.workspace_dir(root, args.workspace)
if not paths.workspace_file(root, args.workspace).is_file():
    parser.error('Select the staging vault with LAB_VAULT and an existing workspace')
url = subprocess.check_output([str(checkout/'scripts/lab-url.sh')], text=True).strip()
parts = urlsplit(url)
if parts.hostname not in {'localhost','127.0.0.1'}:
    raise SystemExit('This staging probe only supports the local Lab server')
url = urlunsplit((parts.scheme, f'127.0.0.1:{parts.port}', '', '', ''))
user = auth.get_user('admin')
if not user:
    raise SystemExit('The local admin account is required for this staging probe')
env = {**os.environ, 'LAB_PROBE_COOKIE': auth.issue_session(user)}
sys.exit(subprocess.call(['node', str(checkout/'scripts/perf/objectives_staging_latency.mjs'), url,
    str(workspace), args.output], env=env))
