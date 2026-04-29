def test_get_search_empty_q(client) -> None:
    r = client.get("/api/search?q=")
    assert r.status_code == 200
    body = r.json()
    assert body["projects"] == []
    assert body["tasks"] == []
    assert body["docs"] == []


def test_get_search_matches_project(client, seed_project) -> None:
    seed_project("alpha", description="contains zebra")
    r = client.get("/api/search?q=zebra")
    assert r.status_code == 200
    body = r.json()
    assert len(body["projects"]) == 1
    assert body["projects"][0]["id"] == "alpha"


def test_get_search_matches_md(client, monorepo) -> None:
    (monorepo / "knowledge" / "meetings" / "n.md").write_text("meeting about zebras\n")
    r = client.get("/api/search?q=zebra")
    body = r.json()
    assert len(body["docs"]) >= 1
