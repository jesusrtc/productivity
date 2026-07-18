# Headless UI check misses the launch-agent server

When Lab is supervised by the macOS launch agent, the live process command is
typically the resolved Homebrew Python executable followed by ``-m core``. It
does not contain the checkout-relative string ``core/.venv/bin/python -m
core`` that ``scripts/check-ui.sh`` checks with ``pgrep``.

As a result, ``make check-ui`` could misclassify the live server as stopped
and try to start a duplicate on the default port.

Fixed 2026-07-18: ``scripts/check-ui.sh`` now probes the URL resolved by
``scripts/lab-url.sh`` (curl, not pgrep) and only auto-starts when nothing
answers, re-resolving the URL afterwards. Probing the URL is the only
detection that works across supervision modes — keep it that way.
