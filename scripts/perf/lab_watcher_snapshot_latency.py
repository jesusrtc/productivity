#!/usr/bin/env python3
"""Compare full polling snapshots/diffs against watchdog on an owned static tree.

This is a component comparison after fixture creation/reference validation,
not a cold UI or physical-display measurement. Both variants use fresh stats;
all alternating samples are retained. Paths, inode maps and every field used
for event detection are checked.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'core/src'))
from core.polling import _PollingSnapshot
from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', type=int, default=5000)
    parser.add_argument('--samples', type=int, default=40)
    args = parser.parse_args()
    if args.files < 1 or args.samples < 2:
        parser.error('At least one file and two samples are required')
    rows = []
    with tempfile.TemporaryDirectory(prefix='lab-watcher-component-') as folder:
        root = Path(folder)
        for number in range(args.files):
            (root / f'entry-{number:05d}.md').write_text(f'Fixture {number}\n')
        reference = DirectorySnapshot(folder)
        for number in range(args.samples):
            variants = [('baseline', DirectorySnapshot), ('candidate', _PollingSnapshot)]
            for name, kind in variants if number % 2 == 0 else reversed(variants):
                start, cpu = time.perf_counter(), time.thread_time()
                snapshot = kind(folder)
                scan_cpu = (time.thread_time() - cpu) * 1000
                scan_ms = (time.perf_counter() - start) * 1000
                assert snapshot.paths == reference.paths
                assert all(snapshot.inode(path) == reference.inode(path)
                           and snapshot.isdir(path) == reference.isdir(path)
                           and snapshot.mtime(path) == reference.mtime(path)
                           and snapshot.size(path) == reference.size(path)
                           and snapshot.path(reference.inode(path)) == reference.path(reference.inode(path))
                           for path in reference.paths)
                start, cpu = time.perf_counter(), time.thread_time()
                diff = DirectorySnapshotDiff(snapshot, snapshot)
                diff_cpu = (time.thread_time() - cpu) * 1000
                diff_ms = (time.perf_counter() - start) * 1000
                assert not any(getattr(diff, f'{kind}_{change}') for kind in ('files', 'dirs')
                               for change in ('created', 'deleted', 'modified', 'moved'))
                rows.append({'variant': name, 'sample': number + 1, 'scanMs': scan_ms,
                             'scanCpuMs': scan_cpu, 'diffMs': diff_ms, 'diffCpuMs': diff_cpu})
    summary = {name: {key: {'median': statistics.median(row[key] for row in rows if row['variant'] == name),
                            'max': max(row[key] for row in rows if row['variant'] == name)}
                      for key in ('scanMs', 'scanCpuMs', 'diffMs', 'diffCpuMs')}
               for name in ('baseline', 'candidate')}
    print(json.dumps({'files': args.files, 'samplesPerVariant': args.samples,
                      'metadataVerified': True, 'summary': summary, 'rows': rows}, indent=2))


if __name__ == '__main__':
    main()
