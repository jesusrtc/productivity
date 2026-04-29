from __future__ import annotations

import json
from pathlib import Path


def _write_notebook(path: Path) -> None:
    """Write a minimal nbformat v4 notebook with one markdown + one code cell.

    We build the JSON directly rather than importing ``nbformat`` so the test
    has no extra dependency. The shape matches what ``parse_notebook`` expects:
    ``source`` as a list of strings, outputs with ``output_type`` set.
    """
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "name": "python3",
                "display_name": "Python 3",
                "language": "python",
            },
            "language_info": {"name": "python"},
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# hi\n", "\n", "this is **bold**"],
            },
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "source": ['print("hello")'],
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": ["hello\n"],
                    }
                ],
            },
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nb))


def test_render_notebook_happy_path(client, monorepo) -> None:
    nb_path = monorepo / "knowledge" / "projects" / "demo" / "notebooks" / "foo.ipynb"
    _write_notebook(nb_path)

    r = client.get("/api/nb?path=knowledge/projects/demo/notebooks/foo.ipynb")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["path"] == "knowledge/projects/demo/notebooks/foo.ipynb"
    assert isinstance(body["mtime"], float)
    assert body["mtime"] > 0

    cells = body["cells"]
    assert len(cells) == 2
    assert [c["cell_type"] for c in cells] == ["markdown", "code"]

    md_cell = cells[0]
    assert "html" in md_cell
    assert isinstance(md_cell["html"], str)
    assert "<h1" in md_cell["html"]
    assert "<strong>" in md_cell["html"]

    code_cell = cells[1]
    assert "print" in code_cell["source"]
    text_outputs = [o for o in code_cell["outputs"] if o.get("type") == "text"]
    assert text_outputs, f"expected a text-typed output, got {code_cell['outputs']!r}"
    assert any("hello" in o["content"] for o in text_outputs)


def test_render_notebook_missing_file(client) -> None:
    r = client.get("/api/nb?path=knowledge/projects/demo/notebooks/nope.ipynb")
    assert r.status_code == 404


def test_render_notebook_rejects_absolute_path(client) -> None:
    r = client.get("/api/nb?path=/etc/passwd.ipynb")
    assert r.status_code == 400


def test_render_notebook_rejects_traversal(client) -> None:
    r = client.get("/api/nb?path=../../etc/foo.ipynb")
    assert r.status_code == 400


def test_render_notebook_rejects_non_ipynb(client, monorepo) -> None:
    path = monorepo / "knowledge" / "projects" / "demo" / "notebooks" / "foo.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("hi")
    r = client.get("/api/nb?path=knowledge/projects/demo/notebooks/foo.txt")
    assert r.status_code == 400
