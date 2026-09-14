from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.diff_parser import parse_notebook_output


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
    nb_path = monorepo / "workspaces" / "demo" / "notebooks" / "foo.ipynb"
    _write_notebook(nb_path)

    r = client.get("/api/nb?path=workspaces/demo/notebooks/foo.ipynb")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["path"] == "workspaces/demo/notebooks/foo.ipynb"
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
    r = client.get("/api/nb?path=workspaces/demo/notebooks/nope.ipynb")
    assert r.status_code == 404


def test_render_notebook_rejects_absolute_path(client) -> None:
    r = client.get("/api/nb?path=/etc/passwd.ipynb")
    assert r.status_code == 400


def test_render_notebook_rejects_traversal(client) -> None:
    r = client.get("/api/nb?path=../../etc/foo.ipynb")
    assert r.status_code == 400


def test_render_notebook_rejects_non_ipynb(client, monorepo) -> None:
    path = monorepo / "workspaces" / "demo" / "notebooks" / "foo.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("hi")
    r = client.get("/api/nb?path=workspaces/demo/notebooks/foo.txt")
    assert r.status_code == 400


def test_live_and_persisted_outputs_share_svg_stream_and_display_shape() -> None:
    stream = parse_notebook_output({
        "output_type": "stream", "name": "stderr", "text": ["warning", "\n"],
    })
    svg = parse_notebook_output({
        "output_type": "display_data",
        "data": {"image/svg+xml": ["<svg>", "<circle />", "</svg>"]},
        "metadata": {},
        "transient": {"display_id": "plot-1"},
    })
    assert stream == {
        "type": "text", "content": "warning\n", "stream_name": "stderr",
    }
    assert svg == {
        "type": "html",
        "content": "<svg><circle /></svg>",
        "display_id": "plot-1",
    }


@pytest.mark.parametrize("output_type", ["display_data", "execute_result"])
def test_plotly_mime_prefers_interactive_output_and_escapes_labels(output_type) -> None:
    figure = {
        "data": [{"type": "scatter", "x": [1, 2], "y": [3, 4]}],
        "layout": {"title": "</script><script>alert('label')</script> & π"},
        "config": {"displayModeBar": False},
        "frames": [{"name": "next", "data": [{"y": [5, 6]}]}],
    }
    raw = {
        "output_type": output_type,
        "data": {
            "application/vnd.plotly.v1+json": figure,
            "text/plain": "Figure(...)",
            "text/html": "<p>fallback</p>",
            "image/png": "fallback",
        },
        "transient": {"display_id": "chart-1"},
    }
    parsed = parse_notebook_output(raw)
    assert parsed["type"] == "html"
    assert parsed["display_id"] == "chart-1"
    html = parsed["content"]
    assert html.count("<script>") == html.count("</script>") == 1
    assert "cdn" not in html
    payload = html.split("var figure = ", 1)[1].split(";function fail", 1)[0]
    assert json.loads(payload) == figure
    assert parse_notebook_output(raw) == parsed  # stable notebook diffs


def test_invalid_plotly_mime_keeps_existing_fallback() -> None:
    assert parse_notebook_output({
        "output_type": "display_data",
        "data": {"application/vnd.plotly.v1+json": None, "text/plain": ["fallback"]},
    }) == {"type": "text", "content": "fallback"}


def test_native_plotly_is_preserved_by_both_notebook_read_routes(client, monorepo) -> None:
    path = monorepo / "workspaces/demo/notebooks/plotly.ipynb"
    _write_notebook(path)
    notebook = json.loads(path.read_text())
    output = {
        "output_type": "display_data",
        "data": {"application/vnd.plotly.v1+json": {"data": [{"y": [1, 3, 2]}]}},
    }
    notebook["cells"][1]["outputs"] = [output]
    path.write_text(json.dumps(notebook))
    expected = [parse_notebook_output(output)]
    live_view = client.get("/api/nb", params={"path": str(path.relative_to(monorepo))})
    file_view = client.get("/api/notebook", params={"repo": str(monorepo), "path": str(path.relative_to(monorepo))})
    assert live_view.status_code == file_view.status_code == 200
    assert live_view.json()["cells"][1]["outputs"] == expected
    assert file_view.json()[1]["outputs"] == expected
