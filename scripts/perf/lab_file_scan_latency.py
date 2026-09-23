#!/usr/bin/env python3
"""Compare complete file-scan results and time on a CLI-created disposable vault.

Alternates a prior route implementation and the candidate without changing the
OS cache. This times the route's filesystem work, not HTTP/auth/serialization.
Use --transport asgi to include FastAPI validation/serialization and its worker
dispatch in an in-process TestClient, without a socket or production middleware.
No first samples are discarded. Provider and real workspace data are untouched.
"""
import argparse
import ast
import contextlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='7eda46a')
    parser.add_argument('--files', type=int, default=2000)
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--transport', choices=['route', 'asgi'], default='route')
    args = parser.parse_args()
    if args.files < 1 or args.samples < 2:
        parser.error('Use at least one file and two samples')

    checkout = Path(__file__).resolve().parents[2]
    source_paths = [str(checkout / 'core/src'), str(checkout / 'core/cli/src')]
    sys.path[:0] = source_paths
    os.environ['PYTHONPATH'] = os.pathsep.join(source_paths + [os.environ.get('PYTHONPATH', '')])
    with contextlib.ExitStack() as stack:
        folder = stack.enter_context(tempfile.TemporaryDirectory(prefix='lab-scan-profile-'))
        root = Path(folder).resolve() / 'vault'
        os.environ.update(
            LAB_HOME=str(root.parent / 'config'), LAB_VAULT=str(root), LAB_ROOT=str(root),
            LAB_ENV_FILE=str(root.parent / 'no.env'), LAB_ASSISTANT_HOME=str(root.parent / 'assistant'),
        )
        os.environ.pop('LAB_WORKSPACE', None)

        def lab(*arguments):
            subprocess.run([sys.executable, '-m', 'lab', *arguments], check=True, stdout=subprocess.DEVNULL)

        lab('init', str(root), '--name', 'Scan fixture', '--no-example', '--no-git')
        lab('workspace', 'new', 'files')
        target = root / 'workspaces/files'
        for number in range(args.files):
            parent = target / 'notes' / str(number // 100)
            parent.mkdir(exist_ok=True)
            (parent / f'file-{number}.md').write_text('# Fixture\n')
        (target / 'docs/link.md').symlink_to(target / 'notes/0/file-0.md')
        (target / 'docs/broken').symlink_to(target / 'missing')

        from core.routes import diff
        from core import auth
        from starlette.requests import Request

        request = Request({
            'type': 'http', 'headers': [],
            'app': SimpleNamespace(state=SimpleNamespace(index_cache=SimpleNamespace(root=root))),
            'state': {'auth_user': auth.get_user('admin')},
        })
        source = subprocess.check_output(
            ['git', 'show', args.baseline + ':core/src/core/routes/diff.py'], cwd=checkout, text=True,
        )
        functions = [
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name in {'api_workspace_files', '_with_symlink_fields'}
        ]
        if len(functions) != 2:
            raise RuntimeError('Baseline must contain the scan and symlink helper')
        baseline_model = None
        for function in functions:
            if function.name == 'api_workspace_files':
                baseline_model = next((
                    keyword.value for decorator in function.decorator_list
                    if isinstance(decorator, ast.Call)
                    for keyword in decorator.keywords if keyword.arg == 'response_model'
                ), None)
            function.decorator_list = []
        namespace = dict(diff.__dict__)
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<baseline>', 'exec'), namespace)
        variants = {'baseline': namespace['api_workspace_files'], 'candidate': diff.api_workspace_files}
        if args.transport == 'asgi':
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.state.index_cache = request.app.state.index_cache

            @app.middleware('http')
            async def fixture_user(incoming, call_next):
                incoming.state.auth_user = request.state.auth_user
                return await call_next(incoming)

            candidate_model = next(
                route.response_model for route in diff.router.routes if route.endpoint is diff.api_workspace_files
            )
            models = {
                'candidate': candidate_model,
                'baseline': eval(compile(ast.Expression(baseline_model), '<baseline model>', 'eval'), namespace)
                if baseline_model is not None else None,
            }
            for name, endpoint in variants.items():
                model = models[name]
                app.add_api_route('/' + name, endpoint, methods=['GET'], response_model=model)
            client = stack.enter_context(TestClient(app))

            def call_asgi(name):
                response = client.get('/' + name, params={'path': str(target)})
                response.raise_for_status()
                return response.json()

            variants = {name: (lambda path, req, name=name: call_asgi(name)) for name in variants}
        durations = {name: [] for name in variants}
        for number in range(args.samples):
            rows = {}
            order = ('baseline', 'candidate') if number % 2 == 0 else ('candidate', 'baseline')
            for name in order:
                start = time.perf_counter()
                rows[name] = variants[name](str(target), request)
                durations[name].append((time.perf_counter() - start) * 1000)
            assert rows['baseline'] == rows['candidate'], 'File scan changed response'
        print(json.dumps({
            'fixture': {
                'files': args.files, 'samples': args.samples,
                'baseline': args.baseline, 'transport': args.transport,
            },
            'responsesEqual': True,
            'stats': {
                name: {'first': values[0], 'p50': statistics.median(values), 'max': max(values)}
                for name, values in durations.items()
            },
        }, indent=2))


if __name__ == '__main__':
    main()
