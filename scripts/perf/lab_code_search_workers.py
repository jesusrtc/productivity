#!/usr/bin/env python3
"""Compare native ripgrep workers on owned dense, sparse and regex workloads.

This measures complete subprocess capture, not HTTP or UI latency. Keep every
sample, rotate variant order, and verify the complete sorted output and status.
Defaults create 5,000 small files and 256 MiB across 64 large files. All fixtures
are removed on success or failure. Explicit worker variants are diagnostic;
production separately preserves regex queries and RIPGREP_CONFIG_PATH settings.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--small-files', type=int, default=5000)
    parser.add_argument('--large-files', type=int, default=64)
    parser.add_argument('--large-mib', type=int, default=4, help='MiB per large file')
    args = parser.parse_args()
    if min(args.samples, args.small_files, args.large_files, args.large_mib) < 1:
        parser.error('Sample and file counts/sizes must be positive')
    if args.output.exists():
        parser.error('Refusing to replace an existing report')
    executable = shutil.which('rg')
    if not executable:
        parser.error('Native ripgrep is required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {
        'scope': 'complete native subprocess capture; no HTTP or browser',
        'executable': executable, 'configPresent': bool(os.environ.get('RIPGREP_CONFIG_PATH')),
        'smallFiles': args.small_files, 'largeFiles': args.large_files,
        'largeMiBPerFile': args.large_mib, 'samples': [], 'fixtureRemoved': False,
    }

    def save():
        args.output.write_text(json.dumps(result, indent=2) + '\n')

    base = None
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='lab-search-workers-') as folder:
            base = Path(folder)
            result['fixturePath'] = str(base)
            small = base / 'small'
            small.mkdir()
            for number in range(args.small_files):
                (small / f'file-{number:05}.txt').write_text(('LAB_MATCH ' + 'x' * 240 + '\n') * 20)
            (small / 'fresh.txt').write_text('FRESH_MARKER café\n')
            large = base / 'large'
            large.mkdir()
            rng = random.Random(789)
            block = ''.join(rng.choices('abcdef0123456789', k=4095)) + '\n'
            payload = block * (args.large_mib * 256)
            for number in range(args.large_files):
                (large / f'file-{number:05}.txt').write_text(payload)
            (large / 'fresh.txt').write_text('FRESH_MARKER café\n')
            workloads = [
                ('dense-small', small, 'LAB_MATCH', args.small_files * 20),
                ('sparse-small', small, 'FRESH_MARKER', 1),
                ('sparse-large', large, 'FRESH_MARKER', 1),
                ('regex-large', large, r'(?:[a-z]{7}[0-9]{7}){3}', 0),
            ]
            for name, root, query, expected in workloads:
                reference = None
                for sample in range(args.samples):
                    variants = [0, 1, 2, 4, 8]
                    start = sample % len(variants)
                    for workers in variants[start:] + variants[:start]:
                        command = [executable, *(['--threads', str(workers)] if workers else []),
                                   '--max-count', '20', '--max-columns', '300', '-n', '--no-heading',
                                   '--color', 'never', '--', query, '.']
                        started = time.perf_counter()
                        proc = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=20)
                        elapsed = (time.perf_counter() - started) * 1000
                        rows = proc.stdout.splitlines()
                        fingerprint = hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()
                        measurement = {'workload': name, 'sample': sample + 1, 'workers': workers or 'default',
                                       'ms': elapsed, 'rows': len(rows), 'sha256Sorted': fingerprint,
                                       'characters': len(proc.stdout), 'returncode': proc.returncode}
                        result['samples'].append(measurement)
                        save()
                        assert len(rows) == expected, (name, workers, len(rows), expected)
                        identity = fingerprint, proc.returncode, proc.stderr
                        if reference is None:
                            reference = identity
                        assert identity == reference, (name, workers)
                        measurement['verified'] = True
                        save()
                print(name, {
                    str(n or 'default'): round(statistics.median(
                        row['ms'] for row in result['samples']
                        if row['workload'] == name and row['workers'] == (n or 'default')
                    ), 3) for n in [0, 1, 2, 4, 8]
                }, flush=True)
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        result['fixtureRemoved'] = base is not None and not base.exists()
        save()


if __name__ == '__main__':
    main()
