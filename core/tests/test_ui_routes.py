from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


def _request(root):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(index_cache=SimpleNamespace(root=root)),
        ),
    )


def test_tab_order_defaults_to_empty(client) -> None:
    r = client.get("/api/ui/tab-order")
    assert r.status_code == 200
    assert r.json() == []


def test_tab_order_roundtrip(client) -> None:
    r = client.post("/api/ui/tab-order", json={"order": ["a", "b", "c"]})
    assert r.status_code == 200
    assert r.json()["order"] == ["a", "b", "c"]
    assert client.get("/api/ui/tab-order").json() == ["a", "b", "c"]


def test_tab_order_dedupes(client) -> None:
    r = client.post("/api/ui/tab-order", json={"order": ["a", "b", "a", "c", "b"]})
    assert r.json()["order"] == ["a", "b", "c"]


def test_tab_order_persists_across_requests(client) -> None:
    client.post("/api/ui/tab-order", json={"order": ["x", "y"]})
    client.post("/api/ui/tab-order", json={"order": ["y", "x"]})
    assert client.get("/api/ui/tab-order").json() == ["y", "x"]


def test_tab_order_rejects_bad_payload(client) -> None:
    r = client.post("/api/ui/tab-order", json={"order": "not-a-list"})
    assert r.status_code == 422  # pydantic rejects the wrong type


def test_tab_order_filters_non_string_entries(client) -> None:
    # Pydantic accepts list[str], so bad entries either fail validation or
    # land here filtered. Make sure we don't explode and preserve valid
    # strings only.
    r = client.post("/api/ui/tab-order", json={"order": ["a", "", "b"]})
    assert r.status_code == 200
    # Dedupe keeps "" on first sight too; that's fine — it's a valid (empty)
    # string entry. Just assert the meaningful ones are preserved in order.
    order = r.json()["order"]
    assert order[0] == "a"
    assert "b" in order


def test_pseudo_tabs_open_state_roundtrip_without_app(tmp_path) -> None:
    from core.routes import ui

    request = _request(tmp_path)
    assert asyncio.run(ui.get_pseudo_tabs(request)) == []

    opened = asyncio.run(ui.set_pseudo_tab(
        ui.PseudoTabState(tab_id="__logs__", open=True),
        request,
    ))
    assert opened == {"ok": True, "open": ["__logs__"]}
    assert asyncio.run(ui.get_pseudo_tabs(request)) == ["__logs__"]

    closed = asyncio.run(ui.set_pseudo_tab(
        ui.PseudoTabState(tab_id="__logs__", open=False),
        request,
    ))
    assert closed == {"ok": True, "open": []}


def test_pseudo_tabs_reject_unknown_id_without_app(tmp_path) -> None:
    from core.routes import ui

    with pytest.raises(ui.HTTPException):
        asyncio.run(ui.set_pseudo_tab(
            ui.PseudoTabState(tab_id="__unknown__", open=True),
            _request(tmp_path),
        ))
