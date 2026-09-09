def test_get_search_empty_q(client) -> None:
    r = client.get("/api/search?q=")
    assert r.status_code == 200
    body = r.json()
    assert body["workspaces"] == []
    assert body["tasks"] == []
    assert body["docs"] == []


def test_get_search_matches_workspace(client, seed_workspace) -> None:
    seed_workspace("alpha", description="contains zebra")
    r = client.get("/api/search?q=zebra")
    assert r.status_code == 200
    body = r.json()
    assert len(body["workspaces"]) == 1
    assert body["workspaces"][0]["id"] == "alpha"


def test_get_search_matches_md(client, monorepo) -> None:
    (monorepo / "content" / "meetings" / "n.md").write_text("meeting about zebras\n")
    r = client.get("/api/search?q=zebra")
    body = r.json()
    assert len(body["docs"]) >= 1
