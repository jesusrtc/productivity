#!/usr/bin/env python3
"""Compare uncached Codex metadata lookups against a git revision on local data.

Uses Home's current live session scope and alternates baseline/candidate order.
Disables only the in-process metadata TTL for each measured call; no provider
file is changed and no conversation text or identifiers are printed. OS file
caches remain warm, so use lab_http_latency.py for first-request measurements.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import time

from core.routes import term

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='perf/response-budget')
    parser.add_argument('--samples', type=int, default=20)
    args = parser.parse_args()
    if args.samples < 2:
        parser.error('Use at least two samples per version')
    source = subprocess.check_output([
        'git', '-C', str(ROOT), 'show',
        args.baseline + ':core/src/core/routes/term.py',
    ], text=True)
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == '_codex_session_metadata_by_tty')
    # The baseline function runs against the same support functions and live
    # inputs. This comparison is for this query change, not arbitrary ref diffs.
    namespace = dict(vars(term))
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline metadata>', 'exec'), namespace)
    baseline = namespace['_codex_session_metadata_by_tty']
    rows = term._home_session_rows(term.lab_paths.find_vault_root())
    ttys = {row['pane_tty'] for row in rows if row.get('agent') == 'codex' and row.get('pane_tty')}
    cwds = {row['cwd'] for row in rows if row.get('agent') == 'codex' and row.get('cwd')}
    if not ttys:
        raise RuntimeError('No live Codex Home terminals; no meaningful benchmark to run')
    versions = {'baseline': baseline, 'candidate': term._codex_session_metadata_by_tty}
    timings = {key: [] for key in versions}
    differences = []
    for index in range(args.samples):
        results = {}
        for key in list(versions) if index % 2 == 0 else list(versions)[::-1]:
            function = versions[key]
            function.__globals__['_CODEX_METADATA_CACHE'] = None
            started = time.perf_counter()
            results[key] = function(ttys, cwds)
            timings[key].append((time.perf_counter() - started) * 1000)
        if results['baseline'] != results['candidate']:
            differences.append(index + 1)
    for key, samples in timings.items():
        ordered = sorted(samples)
        print(json.dumps({
            'version': key, 'samples': len(samples), 'ttys': len(ttys),
            **{label: round(ordered[round((len(ordered)-1)*fraction)], 2)
               for label, fraction in [('p50_ms', .5), ('p95_ms', .95), ('max_ms', 1)]},
            'over_200_ms': [{'sample': i+1, 'ms': round(ms, 2)}
                            for i, ms in enumerate(samples) if ms >= 200],
        }), flush=True)
    print(json.dumps({'different_result_samples': differences,
                      'note': 'Concurrent provider writes can change results between paired calls.'}))
    return int(bool(differences) or any(ms >= 200 for ms in timings['candidate']))


if __name__ == '__main__':
    raise SystemExit(main())
