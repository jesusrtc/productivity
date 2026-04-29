def test_root_serves_index_html(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
    # Post-unification, `/` serves the absorbed gdiff shell.
    assert "<title>Git Diff Viewer</title>" in r.text


def test_static_css_served(client) -> None:
    r = client.get("/static/css/app.css")
    assert r.status_code == 200
    assert "font-family" in r.text


def test_static_js_served(client) -> None:
    r = client.get("/static/js/app.js")
    assert r.status_code == 200
