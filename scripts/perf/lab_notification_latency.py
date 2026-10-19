#!/usr/bin/env python3
"""Measure Home notification clicks on the running local Lab, in disposable Chrome profiles.

Uses existing reports; never sends terminal input or changes server status. Review
state is reset only in each private browser profile. Auto-spawn is disabled there.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from core import auth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=8)
    parser.add_argument('--cold-runs', type=int, default=3)
    parser.add_argument('--history', action='store_true', help='Keep Show all on while checking successive cards')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.samples < 1 or args.cold_runs < 1:
        parser.error('samples and cold-runs must be positive')
    root = Path(__file__).resolve().parents[2]
    base = subprocess.check_output([str(root / 'scripts/lab-url.sh')], text=True).strip()
    owner = auth.get_user(auth.BUILTIN_ADMIN_USERNAME)
    if not owner:
        parser.error('Start the local Lab server first')
    rows = []
    for run in range(args.cold_runs):
        completed = subprocess.run(
            ['node', str(Path(__file__).with_suffix('.mjs')), base, str(args.samples), str(args.history).lower()],
            env={**os.environ, 'LAB_PROBE_COOKIE': auth.issue_session(owner)},
            text=True, capture_output=True, timeout=90, check=True,
        )
        rows.extend({'run': run, **row} for row in json.loads(completed.stdout))
    timings = sorted(row['ms'] for row in rows)
    result = {'samples': rows, 'max_ms': max(timings),
              'p95_ms': timings[max(0, (len(timings)*95+99)//100-1)],
              'under_200_ms': all(row['ms'] < 200 and row['focused'] and row['output']
                                  and (not args.history or row['show_all']) for row in rows)}
    rendered = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end='')
    return 0 if result['under_200_ms'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
