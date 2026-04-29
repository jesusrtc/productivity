#!/usr/bin/env python3
"""Download code files from Darwin — a single file or an entire folder tree.

Accepts a Darwin path or a full Darwin URL. Automatically detects whether
the target is a file or directory.

Usage:
    venv/bin/python3 download.py /jcortes
    venv/bin/python3 download.py "/jcortes/Untitled Folder/Lab/Google Sheet connect.ipynb"
    venv/bin/python3 download.py "https://darwin.prod.linkedin.com/ui/notebook-detail/lab/?path=jcortes/Untitled%20Folder/Lab/Google%20Sheet%20connect.ipynb"
"""

import json
import os
import sys
import getpass
import sqlite3
import time
import threading
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DARWIN_BASE_URL = os.environ.get("DARWIN_HOST", "https://darwin.prod.linkedin.com")
DEFAULT_FABRIC = "prod-ltx1"
EXTENSIONS = {".ipynb", ".py", ".swb"}
OUTPUT_DIR = Path(__file__).parent / "downloads"
MANIFEST_PATH = Path(__file__).parent / "manifest.json"
MAX_WORKERS = 10


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_dvtoken(username=None, fabric=DEFAULT_FABRIC):
    if token := os.environ.get("DARWIN_TOKEN"):
        return token
    user = username or os.environ.get("USER") or getpass.getuser()
    best_token, best_expiry = None, None

    db_path = Path.home() / ".datavault" / ".filecache" / "stored_credential.db"
    if db_path.exists():
        try:
            encoded = user.replace("(", "%28").replace(")", "%29")
            cred_id = f"dv_u%3A%28{encoded}%29f%3A%28{fabric}%29"
            with sqlite3.connect(str(db_path)) as conn:
                row = conn.execute(
                    "SELECT cred_value FROM credentials WHERE cred_id=?", (cred_id,)
                ).fetchone()
            if row:
                data = json.loads(row[0])
                t = data.get("_dv_token_value")
                e = float(data.get("token_expiration_timestamp", 0))
                if t and e:
                    best_token, best_expiry = t, e
        except Exception:
            pass

    cache = Path.home() / ".captain" / f"darwin_token_{user}.json"
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
            t = data.get("_dv_token_value")
            e = float(data.get("token_expiration_timestamp", 0))
            if t and e and (best_expiry is None or e > best_expiry):
                best_token, best_expiry = t, e
        except Exception:
            pass

    if best_token and best_expiry and time.time() < (best_expiry - 300):
        return best_token

    print("\n" + "=" * 60)
    print("ERROR: Darwin token missing or expired.")
    print("Run this command first, then re-run the script:")
    print()
    print("    captain setup darwin")
    print()
    print("=" * 60)
    sys.exit(1)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def contents_url(path):
    user = os.environ.get("USER") or getpass.getuser()
    clean = path.strip("/")
    encoded = quote(clean)
    return f"/user/{user}/api/contents/{encoded}" if encoded else f"/user/{user}/api/contents/"


def find_files(client, path, depth=0, max_depth=10):
    """Recursively find code files. Returns list of (path, last_modified)."""
    if depth > max_depth:
        return []
    try:
        resp = client.get(contents_url(path), params={"contents": "0"})
        resp.raise_for_status()
    except Exception:
        return []
    files = []
    for item in resp.json().get("content", []):
        if item["type"] in ("notebook", "file"):
            if os.path.splitext(item["name"])[1].lower() in EXTENSIONS:
                files.append((item["path"], item.get("last_modified", "")))
        elif item["type"] == "directory":
            files.extend(find_files(client, item["path"], depth + 1, max_depth))
    return files


def load_manifest():
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def save_manifest(manifest):
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")


def download_file(client, darwin_path):
    resp = client.get(contents_url(darwin_path), params={"contents": "1"})
    resp.raise_for_status()
    data = resp.json()

    local_path = OUTPUT_DIR / darwin_path.lstrip("/")
    local_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = data.get("format", "text")
    content = data.get("content")

    if fmt == "json":
        nb = content if isinstance(content, dict) else json.loads(content)
        for cell in nb.get("cells", []):
            if cell.get("outputs"):
                cell["outputs"] = []
            if cell.get("execution_count") is not None:
                cell["execution_count"] = None
        local_path.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    elif fmt == "base64":
        import base64
        local_path.write_bytes(base64.b64decode(content or ""))
    else:
        local_path.write_text(content or "", encoding="utf-8")

    return str(local_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_darwin_input(raw):
    """Extract a Darwin path from a raw argument (path or URL)."""
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        qs = parse_qs(parsed.query)
        if "path" in qs:
            return "/" + unquote(qs["path"][0]).strip("/")
        # Fall back to URL path segments after /ui/...
        sys.exit(f"Could not extract 'path=' from URL: {raw}")
    return "/" + raw.strip("/")


def fetch_item(client, darwin_path):
    """Fetch metadata for a path. Returns the JSON response."""
    resp = client.get(contents_url(darwin_path), params={"contents": "0"})
    resp.raise_for_status()
    return resp.json()


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: venv/bin/python3 download.py <darwin_path_or_url>\n"
                 "  e.g.: venv/bin/python3 download.py /jcortes\n"
                 '        venv/bin/python3 download.py "/jcortes/Untitled Folder/Lab/Google Sheet connect.ipynb"\n'
                 '        venv/bin/python3 download.py "https://darwin.prod.linkedin.com/ui/...?path=jcortes/..."')

    darwin_path = parse_darwin_input(sys.argv[1])

    token = get_dvtoken()
    client = httpx.Client(
        base_url=DARWIN_BASE_URL,
        headers={"Cookie": f"darwin-play-session={token}"},
        timeout=120.0,
    )

    info = fetch_item(client, darwin_path)
    is_file = info.get("type") in ("notebook", "file")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()

    if is_file:
        cached = manifest.get(darwin_path)
        remote_mod = info.get("last_modified", "")
        if cached and cached == remote_mod:
            print(f"Skipping (unchanged): {darwin_path}")
        else:
            print(f"Downloading file: {darwin_path}")
            local = download_file(client, darwin_path)
            manifest[darwin_path] = remote_mod
            save_manifest(manifest)
            print(f"  -> {local}")
        print("Done.")
    else:
        print(f"Discovering files in {darwin_path}/ ...")
        all_files = find_files(client, darwin_path)
        total = len(all_files)

        # Filter to only new/changed files
        to_download = []
        skipped = 0
        for path, last_mod in all_files:
            if manifest.get(path) == last_mod and last_mod:
                skipped += 1
            else:
                to_download.append((path, last_mod))

        print(f"Found {total} code files: {len(to_download)} new/changed, {skipped} unchanged.")

        if not to_download:
            print("Everything up to date.")
            save_manifest(manifest)
            return

        print(f"Downloading with {MAX_WORKERS} threads...")

        lock = threading.Lock()
        counter = {"success": 0, "errors": 0}
        remaining = len(to_download)

        def do_download(item):
            fpath, last_mod = item
            thread_client = httpx.Client(
                base_url=DARWIN_BASE_URL,
                headers={"Cookie": f"darwin-play-session={token}"},
                timeout=120.0,
            )
            try:
                download_file(thread_client, fpath)
                with lock:
                    counter["success"] += 1
                    manifest[fpath] = last_mod
                    done = counter["success"] + counter["errors"]
                    print(f"  [{done}/{remaining}] {fpath}")
            except Exception as e:
                with lock:
                    counter["errors"] += 1
                    done = counter["success"] + counter["errors"]
                    print(f"  [{done}/{remaining}] ERROR {fpath}: {e}")
            finally:
                thread_client.close()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            pool.map(do_download, sorted(to_download))

        save_manifest(manifest)
        print(f"\nDone: {counter['success']} downloaded, {skipped} skipped, {counter['errors']} errors.")
        print(f"Output: {OUTPUT_DIR / darwin_path.strip('/')}")


if __name__ == "__main__":
    main()
