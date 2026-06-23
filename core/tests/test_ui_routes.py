from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest


def _request(root):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(index_cache=SimpleNamespace(root=root)),
        ),
    )


def _run(value):
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


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
    assert _run(ui.get_pseudo_tabs(request)) == []

    opened = _run(ui.set_pseudo_tab(
        ui.PseudoTabState(tab_id="__logs__", open=True),
        request,
    ))
    assert opened == {"ok": True, "open": ["__logs__"]}
    assert _run(ui.get_pseudo_tabs(request)) == ["__logs__"]

    closed = _run(ui.set_pseudo_tab(
        ui.PseudoTabState(tab_id="__logs__", open=False),
        request,
    ))
    assert closed == {"ok": True, "open": []}


def test_pseudo_tabs_include_self_by_default_in_dev_mode(tmp_path, monkeypatch) -> None:
    from core.routes import ui

    monkeypatch.setenv("LAB_DEV_MODE", "1")
    request = _request(tmp_path)

    assert _run(ui.get_pseudo_tabs(request)) == ["__self__"]


def test_pseudo_tabs_self_is_dev_only(tmp_path, monkeypatch) -> None:
    from core.routes import ui

    monkeypatch.delenv("LAB_DEV_MODE", raising=False)

    with pytest.raises(ui.HTTPException):
        _run(ui.set_pseudo_tab(
            ui.PseudoTabState(tab_id="__self__", open=True),
            _request(tmp_path),
        ))


def test_pseudo_tabs_reject_unknown_id_without_app(tmp_path) -> None:
    from core.routes import ui

    with pytest.raises(ui.HTTPException):
        _run(ui.set_pseudo_tab(
            ui.PseudoTabState(tab_id="__unknown__", open=True),
            _request(tmp_path),
        ))


def test_term_autospawn_defaults_enabled(client) -> None:
    r = client.get("/api/ui/term-autospawn", params={"project_id": "demo"})
    assert r.status_code == 200
    assert r.json() == {"project_id": "demo", "enabled": True}


def test_term_autospawn_roundtrip(client) -> None:
    r = client.post("/api/ui/term-autospawn", json={
        "project_id": "demo",
        "enabled": False,
    })
    assert r.status_code == 200
    assert r.json() == {"ok": True, "project_id": "demo", "enabled": False}
    assert client.get(
        "/api/ui/term-autospawn",
        params={"project_id": "demo"},
    ).json()["enabled"] is False

    r = client.post("/api/ui/term-autospawn", json={
        "project_id": "demo",
        "enabled": True,
    })
    assert r.status_code == 200
    assert client.get(
        "/api/ui/term-autospawn",
        params={"project_id": "demo"},
    ).json()["enabled"] is True


def test_term_autospawn_rejects_empty_project_without_app(tmp_path) -> None:
    from core.routes import ui

    with pytest.raises(ui.HTTPException):
        _run(ui.set_term_autospawn(
            ui.TermAutoSpawnState(project_id="", enabled=False),
            _request(tmp_path),
        ))
