#!/usr/bin/env python3
"""Capture all three Git comparison groups in disposable Lab repositories.

Run with core/.venv/bin/python. Creates its vault through the Lab CLI, checks
direct/cached HTTP responses and rendered Chrome rows, and exports screenshots.
Never changes an existing vault, repository, browser profile, or active vault.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time


def git(root, *args):
    return subprocess.check_output([
        'git', '-C', str(root), '-c', 'core.hooksPath=/dev/null',
        '-c', 'commit.gpgsign=false', '-c', 'user.name=Lab Fixture',
        '-c', 'user.email=fixture@example.invalid', *args,
    ], text=True, stderr=subprocess.DEVNULL).strip()


def baseline(root):
    root.mkdir(parents=True)
    git(root, 'init', '-b', 'main')
    for name in ('both-staged.txt', 'both-unstaged.txt', 'uncomm-staged.txt',
                 'uncomm-unstaged.txt', 'committed-only.txt', 'unchanged.txt'):
        (root / name).write_text('main\n')
    (root / '.gitignore').write_text('ignored.txt\n')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Local main baseline')


def changes(root, branch):
    both = ['both-staged.txt', 'both-unstaged.txt', 'both-added.txt']
    uncommitted_only, local_main_only = [], []
    if branch != 'main':
        for name in ('both-staged.txt', 'both-unstaged.txt', 'uncomm-staged.txt',
                     'uncomm-unstaged.txt', 'committed-only.txt',
                     'committed-added.txt', 'both-branch-added.txt'):
            (root / name).write_text(branch + ' commit\n')
        git(root, 'add', '.')
        git(root, 'commit', '-m', 'Changes not merged into local main')
        for name in ('uncomm-staged.txt', 'uncomm-unstaged.txt'):
            (root / name).write_text('main\n')
        git(root, 'add', 'uncomm-staged.txt')
        (root / 'both-branch-added.txt').write_text('edited branch addition\n')
        both.append('both-branch-added.txt')
        uncommitted_only = ['uncomm-staged.txt', 'uncomm-unstaged.txt']
        local_main_only = ['committed-only.txt', 'committed-added.txt']
    (root / 'both-staged.txt').write_text('staged edit\n')
    (root / 'both-unstaged.txt').write_text('unstaged edit\n')
    (root / 'both-added.txt').write_text('staged new file\n')
    git(root, 'add', 'both-staged.txt', 'both-added.txt')
    for name in ('untracked.txt', 'ignored.txt'):
        (root / name).write_text('excluded\n')
    return {'both': sorted(both), 'uncommitted_only': uncommitted_only,
            'local_main_only': local_main_only,
            'uncommitted': sorted(both + uncommitted_only),
            'local-main': sorted(both + local_main_only)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='Evidence directory')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checkout = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='lab-sidebar-comparison-') as directory:
        base = Path(directory).resolve()
        vault = base / 'vault'
        os.environ.update(
            LAB_HOME=str(base / 'config'), LAB_VAULT=str(vault), LAB_ROOT=str(vault),
            LAB_ASSISTANT_HOME=str(base / 'assistant'), LAB_ENV_FILE=str(base / 'no.env'),
            LAB_SERVER_SUPERVISOR='0', LAB_DOCUMENT_TERMINALS_SUPERVISOR='0',
            LAB_TMUX_PREFIX=base.name + '-', LAB_WORKSPACE_WATCHER='off',
        )
        os.environ.pop('LAB_WORKSPACE', None)

        def lab(*args):
            subprocess.run([sys.executable, '-m', 'lab', *args], check=True,
                           stdout=subprocess.DEVNULL)

        lab('init', str(vault), '--name', 'Git comparison fixture', '--no-example', '--no-git')
        lab('workspace', 'new', 'comparisons', '--name', 'Git comparison scenarios')
        lab('config', 'set', 'projectsFolder', str(vault))
        lab('config', 'set', 'worktreesFolder', str(vault / '.worktrees'))
        lab('assistant', 'init')
        lab('assistant', 'migrate', '--apply')
        lab('assistant', 'migrate', '--embedded', '--apply')
        lab('assistant', 'migrate', '--documents', '--apply')
        lab('assistant', 'document', 'add', 'Feature proposal')
        lab('assistant', 'document', 'add', 'Release checklist')
        lab('assistant', 'document', 'add', 'Architecture decisions')
        from lab import assistant_records as records, paths
        assistant = paths.assistant_root()
        proposal = next(row for row in records.records(assistant) if row['title'] == 'Feature proposal')
        lab('assistant', 'subtab', 'add', 'Implementation notes', '--parent', proposal['id'], '--parent-type', 'note')
        child = next(row for row in records.records(assistant) if row['title'] == 'Implementation notes')
        source, metadata, _ = records.resolve(assistant, proposal['path'])
        records.write_document(source, metadata, 'Proposal main document content.\n')
        source, metadata, _ = records.resolve(assistant, child['path'])
        records.write_document(source, metadata, 'Implementation tab content.\n')
        projects = []
        for name in ('main-project', 'feature-project', 'other-project'):
            root = vault / name
            baseline(root)
            projects.append({'path': str(root), 'label': name,
                             'worktreeFolder': str(vault / '.worktrees' / name)})
        main_root, feature_root, other_root = [Path(row['path']) for row in projects]
        git(feature_root, 'checkout', '-b', 'feature')
        git(other_root, 'checkout', '-b', 'other-branch')
        fixtures = []
        for label, project, branch in (
            ('feature-worktree', main_root, 'feature-worktree'),
            ('other-worktree', main_root, 'other-worktree'),
            ('detached-worktree', main_root, 'detached-fixture'),
            ('main-worktree', feature_root, 'main'),
        ):
            root = vault / '.worktrees' / project.name / label
            lab('workspace', 'add', 'comparisons', project.name, '--project-path', str(project),
                '--worktree-path', str(root), '--branch', branch)
            expected = changes(root, branch)
            if label == 'detached-worktree':
                git(root, 'checkout', '--detach')
            fixtures.append({'label': label, 'path': str(root), 'project': str(project),
                             'branch': git(root, 'rev-parse', '--abbrev-ref', 'HEAD'),
                             'expected': expected})
        for label, root, branch in (
            ('main-checkout', main_root, 'main'),
            ('feature-checkout', feature_root, 'feature'),
            ('other-checkout', other_root, 'other-branch'),
        ):
            fixtures.append({'label': label, 'path': str(root), 'project': str(root),
                             'branch': branch, 'expected': changes(root, branch)})
        fixtures.sort(key=lambda row: row['label'])

        import httpx
        import uvicorn
        from core.main import create_app
        from core import auth
        from core.routes import ui
        from types import SimpleNamespace
        external_opens = []
        original_ui_subprocess = ui.subprocess
        ui.subprocess = SimpleNamespace(run=lambda argv, **kwargs: external_opens.append(argv),
            SubprocessError=subprocess.SubprocessError, DEVNULL=subprocess.DEVNULL)
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        os.environ['LAB_PORT'] = str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(create_app(), log_level='error', access_log=False,
                                             ws_per_message_deflate=False))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        report = {'scopes': [], 'browser': None}
        try:
            deadline = time.monotonic() + 20
            while not server.started:
                assert thread.is_alive() and time.monotonic() < deadline, 'Fixture server did not start'
                time.sleep(.01)
            cookie = auth.issue_session(auth.get_user('admin'))
            with httpx.Client(base_url=url, cookies={auth.SESSION_COOKIE: cookie}, timeout=20) as client:
                for fixture in fixtures:
                    row = {key: fixture[key] for key in ('label', 'branch', 'expected')}
                    row['http'] = []
                    for cached in (False, True):
                        for mode in ('uncommitted', 'local-main'):
                            deadline = time.monotonic() + 20
                            while True:
                                response = client.get('/api/sidebar-recent-files', params={
                                    'repo': fixture['path'], 'mode': mode, 'cached': cached,
                                })
                                if response.status_code != 202:
                                    break
                                assert time.monotonic() < deadline
                                time.sleep(.05)
                            assert response.status_code == 200, response.text
                            data = response.json()
                            assert data['available'] and sorted(data['files']) == fixture['expected'][mode], (fixture['label'], mode, data)
                            if cached:
                                assert sorted(entry['path'] for entry in data['entries']) == fixture['expected'][mode]
                            row['http'].append({'mode': mode, 'cached': cached, 'files': sorted(data['files'])})
                    report['scopes'].append(row)
            env = {**os.environ, 'LAB_PROBE_COOKIE': cookie,
                   'LAB_COMPARISON_FIXTURES': json.dumps(fixtures),
                   'LAB_COMPARISON_PROJECTS': json.dumps(projects)}
            env['LAB_COMPARISON_DOCUMENT'] = json.dumps({'document_id':proposal['id'],'tab_id':child['id'],'assistant_root':str(assistant)})
            subprocess.run(['node', str(checkout / 'scripts/check_sidebar_comparisons.mjs'),
                            url, str(vault / 'workspaces/comparisons'), str(output)], env=env, check=True)
            report['browser'] = json.loads((output / 'browser.json').read_text())
            assert [argv[1] for argv in external_opens] == [
                'https://docs.google.com/document/d/fixture/edit',
                'https://tickets.example.invalid/browse/LAB-1']
            report['externalBrowser'] = {'calls':len(external_opens),'launcher':external_opens[0][0],
                'mode':'OS launcher intercepted in this disposable process; no external app opened'}
            print(f"Verified {len(fixtures)} scopes, 28 HTTP comparisons, 14 rendered filters.")
        finally:
            if server.started:
                with httpx.Client(base_url=url, cookies={auth.SESSION_COOKIE: cookie}, timeout=20) as cleanup:
                    response = cleanup.get('/api/term/sessions',params={'workspace_id':'comparisons'})
                    if response.status_code == 200:
                        for session in response.json():
                            if session.get('name','').startswith(base.name+'-'):
                                cleanup.delete('/api/term/sessions/'+session['name'],params={'purge':True})
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), 'Fixture server did not stop'
            (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
            ui.subprocess = original_ui_subprocess
    print('Disposable vault, repositories, worktrees, and server removed.')


if __name__ == '__main__':
    main()
