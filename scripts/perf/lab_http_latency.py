#!/usr/bin/env python3
"""Measure authenticated, read-only HTTP requests against the running local Lab.

Run with core/.venv/bin/python scripts/perf/lab_http_latency.py [API paths...].
Includes the first request and reports every sample exceeding the budget. No
retries, warm-up removal, cached response substitution, or response-body output.
This measures HTTP completion, not browser paint or physical input latency.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit

import httpx

from core import auth

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATHS = [
    '/', '/api/ping', '/api/vaults/workspaces', '/api/term/sessions',
    '/api/term/sessions?workspace_id=__self__',
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*', default=DEFAULT_PATHS)
    parser.add_argument('--base-url', help='Override with an isolated local candidate server')
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--interval', type=float, default=.1, help='Seconds between rounds')
    parser.add_argument('--budget-ms', type=float, default=200)
    args = parser.parse_args()
    if args.samples < 1 or args.interval < 0 or args.budget_ms <= 0:
        parser.error('Use positive samples/budget and a nonnegative interval')
    if any(not path.startswith('/') or path.startswith('//') for path in args.paths):
        parser.error('Paths must be local absolute request paths, such as /api/ping')
    base = args.base_url or subprocess.check_output(
        [str(ROOT / 'scripts/lab-url.sh')], text=True).strip()
    if urlsplit(base).hostname not in {'localhost', '127.0.0.1', '::1'}:
        parser.error('This signed-session benchmark only supports the local Lab server')
    user = auth.get_user(os.environ.get('UI_CHECK_USER', 'admin'))
    if user is None:
        raise RuntimeError('Local benchmark user does not exist')
    rows = {path: [] for path in args.paths}
    with httpx.Client(base_url=base, timeout=30, cookies={
        auth.SESSION_COOKIE: auth.issue_session(user),
    }) as client:
        client.get('/api/auth/me').raise_for_status()
        for index in range(args.samples):
            for path, timings in rows.items():
                start = time.perf_counter()
                response = client.get(path)
                elapsed = (time.perf_counter() - start) * 1000
                response.raise_for_status()
                timings.append(elapsed)
            if index + 1 < args.samples:
                time.sleep(args.interval)
    failed = False
    for path, timings in rows.items():
        ordered = sorted(timings)
        misses = [{'sample': i + 1, 'ms': round(ms, 2)} for i, ms in enumerate(timings)
                  if ms >= args.budget_ms]
        failed |= bool(misses)
        print(json.dumps({
            'path': path, 'samples': len(timings), 'budget_ms': args.budget_ms,
            'first_ms': round(timings[0], 2),
            **{label: round(ordered[round((len(ordered) - 1) * fraction)], 2)
               for label, fraction in [('p50_ms', .5), ('p95_ms', .95), ('max_ms', 1)]},
            'over_budget': misses,
        }), flush=True)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
