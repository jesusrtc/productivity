"""A running backend keeps the shell template that matches its context contract."""
from fastapi.testclient import TestClient

from core import main


def test_index_does_not_hot_load_a_new_backend_context_contract(monorepo, tmp_path, monkeypatch):
    templates = tmp_path / 'templates'
    templates.mkdir()
    index = templates / 'index.html'
    original = (main._TEMPLATES_DIR / 'index.html').read_text()
    index.write_text(original)
    monkeypatch.setattr(main, '_TEMPLATES_DIR', templates)
    monkeypatch.setattr(main, '_INDEX_TEMPLATE_CHECK_INTERVAL_S', 0)
    monkeypatch.setenv('LAB_WORKSPACE_WATCHER', 'off')
    app = main.create_app()
    # Simulate a pull before the first shell request. The old backend cannot
    # supply a variable added by the new template; tojson used to return 500.
    index.write_text(original + '<script>window.newSetting = {{ NEW_SETTING | tojson }};</script>')
    with TestClient(app) as browser:
        assert browser.post('/api/auth/login', json={'username':'admin','password':'admin'}).status_code == 200
        first = browser.get('/')
        assert first.status_code == 200, first.text
        assert 'window.newSetting' not in first.text
        assert 'window.LAB_LINK_SERVICES = [' in first.text
        assert 'window.LAB_NATIVE_BROWSER_REUSE = false;' in first.text
        # Cache invalidation still picks up asset changes without changing the
        # process's template/context pair, including uncached shell variants.
        index.write_text(index.read_text() + '<!-- second pull -->')
        second = browser.get('/?view=assistant')
        assert second.status_code == 200, second.text
        assert 'window.newSetting' not in second.text
