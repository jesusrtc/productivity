from __future__ import annotations

from types import SimpleNamespace

from starlette.datastructures import URL

from core.routes.proxy import _is_self_proxy, _self_proxy_response


def _conn(url: str, server=("127.0.0.1", 8080)):
    return SimpleNamespace(url=URL(url), scope={"server": server, "scheme": "http"})


def test_self_proxy_detects_lab_port_on_localhost() -> None:
    conn = _conn("http://127.0.0.1:8080/api/proxy/demo/8080/")

    assert _is_self_proxy({"host": "localhost", "port": 8080}, conn)
    assert _is_self_proxy({"host": "127.0.0.1", "port": 8080}, conn)
    assert _is_self_proxy({"host": "::1", "port": 8080}, conn)
    assert not _is_self_proxy({"host": "localhost", "port": 5173}, conn)
    assert not _is_self_proxy({"host": "example.com", "port": 8080}, conn)


def test_self_proxy_response_fails_fast_with_explanation() -> None:
    response = _self_proxy_response("demo", "frontend", {"host": "localhost", "port": 8080})

    assert response.status_code == 409
    assert b"Proxy points at Lab itself" in response.body
    assert b"localhost:8080" in response.body
