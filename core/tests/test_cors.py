def test_cors_allows_localhost_origins(client) -> None:
    r = client.get("/api/index", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_preflight(client) -> None:
    r = client.options(
        "/api/index",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in {200, 204}
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
