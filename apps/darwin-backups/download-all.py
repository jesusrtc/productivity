#!/usr/bin/env python3
"""Download all code files from multiple Darwin folders. Skips unchanged files."""

import threading
from concurrent.futures import ThreadPoolExecutor

import httpx

from download import (
    get_dvtoken, find_files, download_file, load_manifest, save_manifest,
    DARWIN_BASE_URL, OUTPUT_DIR, MAX_WORKERS,
)

FOLDERS = [
    "/jcortes",
    "/styang",
    "/sbasole",
    "/adarki",
    "/kjamthe",
    "/avgarg",
    "/acaldero",
    "/gmeyer",
    "/jocostel",
    "/lipy_trustim",
    "/TPD",
    "/sbollier",
    "/rserrato",
    "/tseymour",
]


def download_folder(token, folder, manifest):
    client = httpx.Client(
        base_url=DARWIN_BASE_URL,
        headers={"Cookie": f"darwin-play-session={token}"},
        timeout=120.0,
    )
    try:
        all_files = find_files(client, folder)
    finally:
        client.close()

    if not all_files:
        print(f"  no files found, skipping")
        return 0, 0, 0

    to_download = []
    skipped = 0
    for path, last_mod in all_files:
        if manifest.get(path) == last_mod and last_mod:
            skipped += 1
        else:
            to_download.append((path, last_mod))

    print(f"  {len(all_files)} files: {len(to_download)} new/changed, {skipped} unchanged")

    if not to_download:
        return 0, 0, skipped

    lock = threading.Lock()
    counter = {"success": 0, "errors": 0}

    def do_download(item):
        fpath, last_mod = item
        tc = httpx.Client(
            base_url=DARWIN_BASE_URL,
            headers={"Cookie": f"darwin-play-session={token}"},
            timeout=120.0,
        )
        try:
            download_file(tc, fpath)
            with lock:
                counter["success"] += 1
                manifest[fpath] = last_mod
        except Exception as e:
            with lock:
                counter["errors"] += 1
                print(f"    ERROR {fpath}: {e}")
        finally:
            tc.close()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        pool.map(do_download, sorted(to_download))

    return counter["success"], counter["errors"], skipped


def main():
    token = get_dvtoken()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    total_success = 0
    total_errors = 0
    total_skipped = 0

    for i, folder in enumerate(FOLDERS, 1):
        print(f"\n[{i}/{len(FOLDERS)}] {folder}")
        success, errors, skipped = download_folder(token, folder, manifest)
        total_success += success
        total_errors += errors
        total_skipped += skipped
        if success > 0:
            print(f"  {success} downloaded, {errors} errors")
        save_manifest(manifest)

    print(f"\n{'='*60}")
    print(f"DONE")
    print(f"  Downloaded: {total_success}")
    print(f"  Skipped:    {total_skipped} (unchanged)")
    print(f"  Errors:     {total_errors}")
    print(f"  Output:     {OUTPUT_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
