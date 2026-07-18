# Headless UI check misses the launch-agent server

When Lab is supervised by the macOS launch agent, the live process command is
typically the resolved Homebrew Python executable followed by ``-m core``. It
does not contain the checkout-relative string ``core/.venv/bin/python -m
core`` that ``scripts/check-ui.sh`` checks with ``pgrep``.

As a result, ``make check-ui`` can misclassify the live server as stopped and
try to start a duplicate on the default port. Resolve the target URL with
``scripts/lab-url.sh`` and verify the bound port directly, or fix the script's
server detection before relying on its auto-start branch.
