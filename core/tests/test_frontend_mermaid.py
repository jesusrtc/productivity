"""Load the actual vendored bundle alongside Lab's actual notebook loader."""
from pathlib import Path
import json
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("with_notebook_loader", [False, True])
def test_mermaid_initializes_without_breaking_notebook_modules(with_notebook_loader):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required")
    template = (ROOT / "core/src/core/templates/index.html").read_text()
    shim = template[template.index("    function installLabAmdShim()"):
                    template.index("    function loadLabApp()")]
    app = (ROOT / "core/src/core/static/js/lab-app.js").read_text()
    asset = re.search(r"loadScriptOnce\('(/static/vendor/mermaid[^']+)'\)", app)[1]
    bundle = ROOT / "core/src/core" / asset.lstrip("/")
    script = """
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const page = {console, setTimeout, clearTimeout, queueMicrotask};
page.window = page;
vm.createContext(page);
"""
    if with_notebook_loader:
        script += f"vm.runInContext({json.dumps(shim + 'installLabAmdShim();')}, page);\n"
        script += """
page.define('lab-test-before', [], () => 41);
const originalDefine = page.define, originalRequire = page.require;
"""
    script += f"vm.runInContext(fs.readFileSync({json.dumps(str(bundle))}, 'utf8'), page);\n"
    script += """
assert.equal(typeof page.mermaid.render, 'function');
page.mermaid.initialize({startOnLoad: false, securityLevel: 'strict'});
"""
    if with_notebook_loader:
        script += """
assert.equal(page.define, originalDefine);
assert.equal(page.require, originalRequire);
page.define('lab-test-after', ['lab-test-before'], value => value + 1);
assert.equal(page.require('lab-test-after'), 42);
"""
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
