# Darwin Backups

Download code files (.ipynb, .py, .swb) from Darwin to your local machine.

## Setup

```bash
./setup.sh
```

This creates a Python virtual environment and installs dependencies.

## Usage

Pass a Darwin folder path or a full Darwin URL:

```bash
# Download an entire folder (including subfolders)
./download.py /jcortes
./download.py "/jcortes/Untitled Folder/Lab"

# Paste a Darwin URL directly
./download.py "https://darwin.prod.linkedin.com/ui/notebook-detail/lab/?path=jcortes/Untitled%20Folder/Lab/Google%20Sheet%20connect.ipynb"
```

Files are saved to `downloads/` preserving the original folder structure. Notebook outputs are stripped automatically.

## Prerequisites

A valid Darwin token is required. If you see a token error, run:

```bash
captain setup darwin
```

Then re-run the download.

## Monorepo integration note

Installed to `~/.local/bin/darwin-backups` via `make install` at the monorepo root. The `downloads/` subtree is gitignored — populate with `darwin-backups download`.
