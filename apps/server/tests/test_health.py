def test_ping(client) -> None:
    r = client.get("/api/ping")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
