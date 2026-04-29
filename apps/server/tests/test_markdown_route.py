def test_render_plain_markdown(client, monorepo) -> None:
    path = monorepo / "content" / "meetings" / "hello.md"
    path.write_text("# Hello\n\nWorld")
    r = client.get("/api/markdown?path=content/meetings/hello.md")
    assert r.status_code == 200
    body = r.json()
    assert "Hello</h1>" in body["html"]
    assert body["frontmatter"] == {}


def test_render_with_frontmatter(client, monorepo) -> None:
    path = monorepo / "content" / "meetings" / "fm.md"
    path.write_text("---\ntitle: Test\ntags: [a, b]\n---\n\n# Body")
    r = client.get("/api/markdown?path=content/meetings/fm.md")
    body = r.json()
    assert body["frontmatter"] == {"title": "Test", "tags": ["a", "b"]}
    assert "Body</h1>" in body["html"]


def test_render_missing_file(client) -> None:
    r = client.get("/api/markdown?path=content/meetings/nope.md")
    assert r.status_code == 404


def test_render_rejects_traversal(client) -> None:
    r = client.get("/api/markdown?path=../etc/passwd")
    assert r.status_code == 400
    r = client.get("/api/markdown?path=/etc/passwd")
    assert r.status_code == 400


def test_render_rejects_non_markdown(client, monorepo) -> None:
    path = monorepo / "content" / "meetings" / "hello.txt"
    path.write_text("hi")
    r = client.get("/api/markdown?path=content/meetings/hello.txt")
    assert r.status_code == 400
