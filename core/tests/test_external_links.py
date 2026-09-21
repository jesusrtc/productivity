from __future__ import annotations

import subprocess
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from core import auth
from core.routes import ui


@contextmanager
def _browser_client(client, host="127.0.0.1", base_url="http://localhost"):
    browser = TestClient(client.app, base_url=base_url, client=(host, 50000))
    browser.cookies.set(auth.SESSION_COOKIE, auth.issue_session(auth.get_user("admin")))
    try:
        yield browser
    finally:
        browser.close()


def test_external_link_uses_system_browser_and_preserves_url(client, monkeypatch):
    calls = []
    monkeypatch.setattr(ui.sys, "platform", "darwin")
    monkeypatch.setattr(ui.subprocess, "run", lambda argv, **kwargs: calls.append((argv, kwargs)))
    url = "https://example.com/a?q=one&next=two#section"
    with _browser_client(client) as browser:
        response = browser.post("/api/ui/open-external", json={"url": url}, headers={"Origin": "http://localhost"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls[0][0] == ["/usr/bin/open", url]
    assert not calls[0][1].get("shell")


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///tmp/test", "data:text/html,hi", "--help", "/relative"])
def test_external_link_rejects_non_web_targets(client, monkeypatch, url):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid URLs must never launch an application")
    monkeypatch.setattr(ui.subprocess, "run", unexpected)
    with _browser_client(client) as browser:
        response = browser.post("/api/ui/open-external", json={"url": url}, headers={"Origin": "http://localhost"})
    assert response.status_code == 422


@pytest.mark.parametrize("host,base_url,origin", [
    ("10.0.0.8", "http://localhost", "http://localhost"),
    ("127.0.0.1", "https://lab.example", "https://lab.example"),
    ("127.0.0.1", "http://localhost", "https://example.com"),
    ("127.0.0.1", "http://localhost", "http://localhost:9999"),
    ("127.0.0.1", "http://localhost", ""),
])
def test_external_link_requires_local_same_origin_session(client, monkeypatch, host, base_url, origin):
    def unexpected(*args, **kwargs):
        pytest.fail("Nonlocal or cross-origin requests must not launch a browser")
    monkeypatch.setattr(ui.subprocess, "run", unexpected)
    with _browser_client(client, host, base_url) as browser:
        response = browser.post("/api/ui/open-external", json={"url": "https://example.com"}, headers={"Origin": origin})
    assert response.status_code == 403


def test_external_browser_capability_is_not_cached_between_local_and_remote(client):
    with _browser_client(client) as local, _browser_client(client, "10.0.0.8") as remote:
        for browser, expected in [(local, "true"), (remote, "false"), (local, "true")]:
            html = browser.get("/").text
            assert f"window.LAB_EXTERNAL_BROWSER = {expected};" in html
            assert "/static/js/lib/external-links.js?v=" in html


def test_external_link_reports_launch_failure(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "open")
    monkeypatch.setattr(ui.subprocess, "run", unavailable)
    with _browser_client(client) as browser:
        response = browser.post("/api/ui/open-external", json={"url": "https://example.com"}, headers={"Origin": "http://localhost"})
    assert response.status_code == 503


def test_external_link_requires_login_and_admin(client, monkeypatch):
    monkeypatch.setattr(ui, "can_open_external", lambda request: True)
    client.post("/api/admin/users", json={"username": "reader", "password": "reader", "role": "user", "vaults": []})
    client.post("/api/auth/logout")
    payload = {"json": {"url": "https://example.com"}, "headers": {"Origin": "http://localhost"}}
    assert client.post("/api/ui/open-external", **payload).status_code == 401
    client.post("/api/auth/login", json={"username": "reader", "password": "reader"})
    assert client.post("/api/ui/open-external", **payload).status_code == 403
