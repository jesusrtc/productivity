"""A running backend keeps the shell template that matches its context contract."""
import os
import re
import shutil
import time

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


def test_objective_assets_invalidate_shell_and_sandbox(monorepo, tmp_path, monkeypatch):
    static = tmp_path / 'static'
    shutil.copytree(main._STATIC_DIR, static)
    monkeypatch.setattr(main, '_STATIC_DIR', static)
    monkeypatch.setattr(main, '_INDEX_TEMPLATE_CHECK_INTERVAL_S', 0)
    monkeypatch.setenv('LAB_WORKSPACE_WATCHER', 'off')
    assets = (
        'js/lib/workspace-objectives.js', 'css/workspace-objectives.css',
        'js/views/objectives-demo.js', 'css/objectives-demo.css',
        'demos/objectives/index.html', 'demos/objectives/objectives.js',
        'demos/objectives/objectives.css',
    )
    with TestClient(main.create_app()) as browser:
        assert browser.post('/api/auth/login', json={'username':'admin','password':'admin'}).status_code == 200

        def version():
            response = browser.get('/')
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-cache'
            return re.search(r'workspace-objectives\.js\?v=([^"\s]+)', response.text)[1]

        previous = version()
        future = time.time_ns() + 10_000_000_000
        for i, asset in enumerate(assets):
            stamp = future + i * 1_000_000_000
            os.utime(static / asset, ns=(stamp, stamp))
            current = version()
            assert current != previous, asset
            previous = current

        sandbox = browser.get('/static/demos/objectives/index.html', params={'v':current})
        assert sandbox.status_code == 200
        assert sandbox.headers['cache-control'] == 'no-cache'
        requests = re.findall(r'(?:src|href)="([^"]+)"', sandbox.text)
        assert len(requests) == 7
        assert all(url.endswith('?v=' + current) for url in requests)
        assert any('lab-markdown-editor/markdown-editor.min.js' in url for url in requests)
