"""Tests for the logging pipeline: ``_JsonFormatter`` + ``/api/log/client``.

The server writes structured JSONL logs split by source and severity:
backend regular logs, frontend regular logs, and errors-only logs. Two pieces
to cover:

- The **formatter** must produce one-line records with the documented
  shape (ts, level, logger, source, msg, path, optional exc/session_id)
  and must not crash on awkward inputs (non-UTF8 bytes, circular refs,
  enormous payloads). A crash inside a log handler takes the whole
  request down, so this is reliability-critical.
- The **ingest endpoint** must cap batch sizes, enforce rate limits,
  reject malformed input, and serialize concurrent writes without
  interleaving (file handler takes a lock internally — this test just
  verifies the contract holds end to end).
"""
from __future__ import annotations

import io
import json
import logging
import logging.handlers
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        if line.strip().startswith("{"):
            rows.append(json.loads(line))
    return rows


# ─── _JsonFormatter unit tests ─────────────────────────────────────────────


class TestJsonFormatter:
    """Direct unit tests against the formatter instance — no file handler,
    no network, just string → dict round-trips. Fast + deterministic."""

    def _format(self, record: logging.LogRecord) -> dict:
        from core.main import _JsonFormatter
        out = _JsonFormatter().format(record)
        # One JSON object per line — no trailing newline, no extras.
        assert "\n" not in out, "formatter must produce a single line"
        return json.loads(out)

    def _make_record(self, *, name="core.term", level=logging.WARNING,
                     msg="hello", extra=None, exc_info=None):
        rec = logging.LogRecord(name=name, level=level, pathname="x.py",
                                lineno=42, msg=msg, args=(), exc_info=exc_info)
        if extra:
            for k, v in extra.items():
                setattr(rec, k, v)
        return rec

    def test_shape_server_side(self):
        rec = self._make_record(msg="boom")
        d = self._format(rec)
        assert set(d.keys()) >= {"ts", "level", "logger", "source", "msg", "path"}
        assert d["level"] == "WARNING"
        assert d["logger"] == "core.term"
        assert d["source"] == "server"
        assert d["msg"] == "boom"
        assert ":42" in d["path"], f"server path should be file:lineno, got {d['path']!r}"

    def test_shape_client_source(self):
        rec = self._make_record(
            name="core.client_errors",
            msg="TypeError: undefined is not a function",
            extra={"source": "client", "path_info": "/?project=xyz",
                   "session_id": "abc-123"},
        )
        d = self._format(rec)
        assert d["source"] == "client"
        assert d["path"] == "/?project=xyz"
        assert d["session_id"] == "abc-123"

    def test_request_path_info_wins_for_server_records(self):
        rec = self._make_record(
            name="core.http",
            level=logging.INFO,
            msg="HTTP GET /api/ping -> 200",
            extra={
                "path_info": "/api/ping",
                "method": "GET",
                "status_code": 200,
                "duration_ms": 1.25,
                "route": "/api/ping",
            },
        )
        d = self._format(rec)
        assert d["source"] == "server"
        assert d["path"] == "/api/ping"
        assert d["method"] == "GET"
        assert d["status_code"] == 200
        assert d["duration_ms"] == 1.25
        assert d["route"] == "/api/ping"

    def test_ts_is_iso8601_with_tz(self):
        d = self._format(self._make_record())
        # isoformat with timezone suffix → ends with +00:00 (UTC).
        assert d["ts"].endswith("+00:00"), d["ts"]

    def test_exc_info_included(self):
        try:
            raise RuntimeError("kaboom")
        except RuntimeError:
            import sys
            rec = self._make_record(level=logging.ERROR, exc_info=sys.exc_info())
        d = self._format(rec)
        assert "exc" in d
        assert "RuntimeError: kaboom" in d["exc"]

    def test_message_with_format_args_resolves(self):
        rec = logging.LogRecord(name="x", level=logging.WARNING, pathname="y.py",
                                lineno=1, msg="count=%d", args=(7,), exc_info=None)
        d = self._format(rec)
        assert d["msg"] == "count=7"

    def test_unicode_preserved_not_escaped(self):
        rec = self._make_record(msg="café → 🧠")
        raw = logging.getLogger("unused")  # silence
        from core.main import _JsonFormatter
        # ensure_ascii=False was an explicit choice in the formatter.
        line = _JsonFormatter().format(rec)
        assert "café" in line and "🧠" in line

    def test_long_message_not_truncated_by_formatter(self):
        """Truncation is the INGEST's job (4000 chars in routes/log.py),
        not the formatter's. If a 4001-char message reaches the formatter
        we still serialize it cleanly."""
        rec = self._make_record(msg="x" * 4001)
        d = self._format(rec)
        assert len(d["msg"]) == 4001

    def test_formatter_survives_bad_exc_chain(self):
        """An exc_info tuple with a broken traceback shouldn't crash the
        handler. Standard library's ``formatException`` is robust but we
        guard here because a crash inside a handler is catastrophic."""
        from core.main import _JsonFormatter
        # Pass an exc_info whose traceback is None (valid per the spec
        # — logging.py allows exc_info=(type, value, None)).
        rec = self._make_record(
            level=logging.ERROR,
            exc_info=(RuntimeError, RuntimeError("no-tb"), None),
        )
        line = _JsonFormatter().format(rec)
        d = json.loads(line)
        assert "RuntimeError" in d["exc"]


# ─── /api/log/client ingest endpoint ────────────────────────────────────────


class TestClientLogIngest:
    """End-to-end through FastAPI. We re-use the existing ``client``
    fixture (and therefore the real lifespan hook that attaches the
    rotating file handler under ``<monorepo>/logs/server.log``). Tests
    assert both the HTTP contract and, where relevant, the file output."""

    def test_happy_path_records_to_file(self, client, monorepo: Path):
        r = client.post("/api/log/client", json={"events": [
            {"level": "error", "msg": "Uncaught TypeError: foo", "path": "/?x=1"},
            {"level": "warning", "msg": "deprecated API",         "path": "/?x=1"},
        ]})
        assert r.status_code == 200
        body = r.json()
        assert body == {"ok": True, "logged": 2}

        log_file = monorepo / "logs" / "server.log"
        # Lifespan created the dir + handler; writes flush on close but
        # WARNING/ERROR via the rotating handler is line-buffered and
        # reaches disk immediately. Give it a tick just in case.
        assert log_file.exists(), "server.log should be created by lifespan"
        frontend = _jsonl(monorepo / "logs" / "frontend.log")
        assert any(r["msg"] == "Uncaught TypeError: foo" and r["level"] == "ERROR" for r in frontend)
        assert any(r["msg"] == "deprecated API" and r["level"] == "WARNING" for r in frontend)
        errors = _jsonl(monorepo / "logs" / "errors.log")
        assert any(r["source"] == "client" and r["msg"] == "Uncaught TypeError: foo" for r in errors)
        assert not any(r["msg"] == "deprecated API" for r in errors)

    def test_empty_batch_ok_but_zero_logged(self, client):
        r = client.post("/api/log/client", json={"events": []})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "logged": 0}

    def test_batch_over_50_is_clamped(self, client):
        events = [{"level": "error", "msg": f"e{i}"} for i in range(120)]
        r = client.post("/api/log/client", json={"events": events})
        assert r.status_code == 200
        # Server clamps to 50 before logging.
        assert r.json()["logged"] == 50

    def test_malformed_json_rejected(self, client):
        r = client.post("/api/log/client", content="{not json",
                        headers={"Content-Type": "application/json"})
        # Pydantic → 422.
        assert r.status_code == 422

    def test_missing_events_field_rejected(self, client):
        r = client.post("/api/log/client", json={})
        # Pydantic requires `events`.
        assert r.status_code == 422

    def test_missing_msg_rejected(self, client):
        r = client.post("/api/log/client", json={"events": [{"level": "error"}]})
        assert r.status_code == 422

    def test_runaway_msg_truncated_not_crashing(self, client):
        """A 10 KB message must not crash the handler — it gets truncated
        to 4 KB by the ingest route. This is the sort of thing a runaway
        browser error loop would emit."""
        r = client.post("/api/log/client", json={"events": [
            {"level": "error", "msg": "X" * 10_000, "path": "/"},
        ]})
        assert r.status_code == 200
        assert r.json()["logged"] == 1

    def test_rate_limit_trips_past_threshold(self, client, monkeypatch):
        """Reset the rate-limit counters, then post >200 events; the
        over-the-line batch must report ``rate_limited``."""
        from core.routes import log as log_route

        # Reset counters so this test is deterministic regardless of what
        # other tests in the session did.
        monkeypatch.setattr(log_route, "_rate_count", 0, raising=False)
        monkeypatch.setattr(log_route, "_rate_window_start", 0.0, raising=False)

        # Post 5 batches of 50 = 250 events total.
        for i in range(5):
            r = client.post("/api/log/client", json={"events": [
                {"level": "error", "msg": f"{i}-{j}"} for j in range(50)
            ]})
            assert r.status_code == 200
        # The 5th batch pushed past the 200-event window; it replied
        # rate_limited (200). The 4th batch is the last that gets logged.
        body = r.json()
        assert body.get("ok") is False and body.get("reason") == "rate_limited"

    def test_level_mapping_error_vs_warning(self, client, monkeypatch):
        """``level`` maps predictably without promoting typos to warnings."""
        import logging as stdlog
        captured = []

        class Cap(stdlog.Handler):
            def emit(self, record):
                captured.append(record.levelno)

        cap = Cap()
        stdlog.getLogger("core.client_errors").addHandler(cap)
        try:
            # Reset rate limit.
            from core.routes import log as log_route
            monkeypatch.setattr(log_route, "_rate_count", 0, raising=False)
            monkeypatch.setattr(log_route, "_rate_window_start", 0.0, raising=False)

            client.post("/api/log/client", json={"events": [
                {"level": "error",   "msg": "a"},
                {"level": "warning", "msg": "b"},
                {"level": "warn",    "msg": "c"},
                {"level": "banana",  "msg": "d"},
            ]})
        finally:
            stdlog.getLogger("core.client_errors").removeHandler(cap)
        assert captured[0] == stdlog.ERROR
        assert captured[1] == stdlog.WARNING
        assert captured[2] == stdlog.WARNING
        assert captured[3] == stdlog.INFO

    def test_info_action_fields_land_in_frontend_regular_log(self, client, monorepo: Path):
        r = client.post("/api/log/client", json={"events": [{
            "level": "info",
            "msg": "client action: click",
            "path": "/#/p/demo",
            "action": "click",
            "target": "button \"Run\"",
            "event_type": "click",
            "href": "#/p/demo",
            "method": "POST",
            "status_code": 200,
            "duration_ms": 12.5,
        }]})
        assert r.status_code == 200
        assert r.json()["logged"] == 1

        frontend = _jsonl(monorepo / "logs" / "frontend.log")
        rec = next(r for r in frontend if r.get("msg") == "client action: click")
        assert rec["level"] == "INFO"
        assert rec["source"] == "client"
        assert rec["path"] == "/#/p/demo"
        assert rec["action"] == "click"
        assert rec["target"] == "button \"Run\""
        assert rec["event_type"] == "click"
        assert rec["href"] == "#/p/demo"
        assert rec["method"] == "POST"
        assert rec["status_code"] == 200
        assert rec["duration_ms"] == 12.5
        assert not _jsonl(monorepo / "logs" / "frontend-errors.log")
        assert not _jsonl(monorepo / "logs" / "errors.log")

    def test_concurrent_writes_produce_valid_jsonl(self, client, monkeypatch, monorepo: Path):
        """Fire 50 concurrent POSTs. Each line in server.log that comes
        from our ingest must be parseable JSON — no interleaving mid-line.
        The RotatingFileHandler takes a lock internally; this test just
        guards against a regression if that contract ever changes."""
        from core.routes import log as log_route

        # Reset rate limit + raise the cap for this test; otherwise we'd
        # hit the 200-event ceiling before covering the concurrency shape.
        monkeypatch.setattr(log_route, "_rate_count", 0, raising=False)
        monkeypatch.setattr(log_route, "_rate_window_start", 0.0, raising=False)
        monkeypatch.setattr(log_route, "_RATE_LIMIT", 10_000, raising=False)

        def _post(i: int):
            return client.post("/api/log/client", json={"events": [
                {"level": "error", "msg": f"conc-{i}-{j}"} for j in range(5)
            ]}).status_code

        with ThreadPoolExecutor(max_workers=16) as pool:
            codes = list(pool.map(_post, range(50)))
        assert all(c == 200 for c in codes)

        log_file = monorepo / "logs" / "server.log"
        assert log_file.exists()
        # Every non-empty line must parse cleanly as JSON. Uvicorn startup
        # lines don't go through our JSON formatter (different handler
        # chain), so we filter to lines that at least look like objects.
        for line in log_file.read_text().splitlines():
            if not line.strip() or not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"invalid JSON line in server.log: {line!r} ({e})")
            assert "msg" in obj, f"missing msg in {obj}"


# ─── Backend request logging ───────────────────────────────────────────────


class TestBackendRequestLogging:
    def test_successful_http_endpoint_logged_to_backend_regular_file(self, client, monorepo: Path):
        r = client.get("/api/ping")
        assert r.status_code == 200

        backend = _jsonl(monorepo / "logs" / "backend.log")
        rec = next(r for r in backend if r.get("path") == "/api/ping")
        assert rec["source"] == "server"
        assert rec["logger"] == "core.http"
        assert rec["level"] == "INFO"
        assert rec["method"] == "GET"
        assert rec["status_code"] == 200
        assert rec["route"] == "/api/ping"
        assert isinstance(rec["duration_ms"], (int, float))
        assert not _jsonl(monorepo / "logs" / "errors.log")

    def test_404_is_warning_not_error_only(self, client, monorepo: Path):
        r = client.get("/missing")
        assert r.status_code == 404

        backend = _jsonl(monorepo / "logs" / "backend.log")
        rec = next(r for r in backend if r.get("path") == "/missing")
        assert rec["level"] == "WARNING"
        assert rec["status_code"] == 404
        assert not _jsonl(monorepo / "logs" / "backend-errors.log")
        assert not _jsonl(monorepo / "logs" / "errors.log")

    def test_unhandled_exception_logged_to_errors_only_file(self, monorepo: Path):
        from fastapi.testclient import TestClient

        from core.main import create_app

        app = create_app()

        @app.get("/boom")
        async def boom():
            raise RuntimeError("boom")

        with TestClient(app, raise_server_exceptions=False) as raw:
            r = raw.get("/boom")
        assert r.status_code == 500

        errors = _jsonl(monorepo / "logs" / "errors.log")
        rec = next(r for r in errors if r.get("path") == "/boom")
        assert rec["level"] == "ERROR"
        assert rec["source"] == "server"
        assert rec["method"] == "GET"
        assert rec["status_code"] == 500
        assert "RuntimeError: boom" in rec["exc"]


# ─── Log tail API / viewer ─────────────────────────────────────────────────


class TestLogTailApi:
    def test_log_files_lists_whitelisted_logs(self, client):
        r = client.get("/api/log/files")
        assert r.status_code == 200
        body = r.json()
        assert body["default_file"] == "errors.log"
        assert body["default_tail"] == 500
        names = {f["name"] for f in body["files"]}
        assert {"errors.log", "backend-errors.log", "frontend-errors.log"} <= names

    def test_log_tail_reads_configured_tail_from_error_file(self, client, monorepo: Path):
        path = monorepo / "logs" / "errors.log"
        rows = [
            {"level": "ERROR", "msg": "old", "path": "/old"},
            {"level": "ERROR", "msg": "newer", "path": "/newer"},
            {"level": "ERROR", "msg": "newest", "path": "/newest"},
        ]
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

        r = client.get("/api/log/tail?file=errors.log&tail=2")
        assert r.status_code == 200
        body = r.json()
        assert body["file"] == "errors.log"
        assert body["tail"] == 2
        assert body["line_count"] == 2
        assert body["state"]["file"] == "errors.log"
        assert body["state"]["exists"] is True
        assert body["state"]["cursor"].startswith("errors.log:")
        assert [e["msg"] for e in body["entries"]] == ["newer", "newest"]

    def test_error_state_cursor_changes_when_error_log_changes(self, client, monorepo: Path):
        path = monorepo / "logs" / "errors.log"
        path.write_text(json.dumps({"level": "ERROR", "msg": "first"}) + "\n")

        first = client.get("/api/log/error-state")
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["exists"] is True
        assert first_body["size"] > 0

        path.write_text(path.read_text() + json.dumps({"level": "ERROR", "msg": "second"}) + "\n")

        second = client.get("/api/log/error-state")
        assert second.status_code == 200
        assert second.json()["cursor"] != first_body["cursor"]

    def test_log_tail_preserves_raw_non_json_lines(self, client, monorepo: Path):
        path = monorepo / "logs" / "errors.log"
        path.write_text("not json\n")

        r = client.get("/api/log/tail?file=errors.log&tail=1")
        assert r.status_code == 200
        assert r.json()["entries"] == [{"raw": "not json"}]

    def test_log_tail_rejects_path_traversal(self, client):
        r = client.get("/api/log/tail?file=../project.json&tail=10")
        assert r.status_code == 400

    def test_log_viewer_page_served(self, client):
        r = client.get("/logs?file=errors.log&tail=25")
        assert r.status_code == 200
        assert '<main id="view"></main>' in r.text
        assert "/static/js/lib/error-report.js" in r.text
        assert "/static/js/lib/log-alert.js" in r.text
        assert "/static/js/views/logs.js" in r.text


# ─── RotatingFileHandler survives rollover ─────────────────────────────────


class TestRotationSurvival:
    """When the log file hits ``maxBytes``, ``RotatingFileHandler`` renames
    it and opens a new stream. The next record must NOT be dropped — a
    regression here would silently lose client error reports."""

    def test_rollover_preserves_subsequent_writes(self, tmp_path: Path):
        from core.main import _JsonFormatter

        logger = logging.getLogger("test.rollover")
        logger.setLevel(logging.WARNING)
        # Small maxBytes so we roll over in the test window.
        h = logging.handlers.RotatingFileHandler(
            tmp_path / "srv.log", maxBytes=200, backupCount=2, encoding="utf-8",
        )
        h.setFormatter(_JsonFormatter())
        logger.addHandler(h)
        try:
            for i in range(50):
                logger.warning("filler %03d - padding to force rollover", i)
            logger.error("LAST_RECORD_SENTINEL")
        finally:
            logger.removeHandler(h)
            h.close()

        # The sentinel must appear in one of the files — current or rotated.
        files = sorted(tmp_path.glob("srv.log*"))
        assert files, "at least one log file should exist"
        found = any("LAST_RECORD_SENTINEL" in f.read_text() for f in files)
        assert found, f"sentinel missing from rotated logs: {[f.name for f in files]}"

    def test_rotation_produces_backup_files(self, tmp_path: Path):
        from core.main import _JsonFormatter

        logger = logging.getLogger("test.rollover2")
        logger.setLevel(logging.WARNING)
        h = logging.handlers.RotatingFileHandler(
            tmp_path / "srv.log", maxBytes=150, backupCount=3, encoding="utf-8",
        )
        h.setFormatter(_JsonFormatter())
        logger.addHandler(h)
        try:
            for i in range(200):
                logger.warning("fill-%02d", i)
        finally:
            logger.removeHandler(h)
            h.close()
        backups = sorted(tmp_path.glob("srv.log.*"))
        assert backups, "expected at least one .1/.2/.3 backup after 200 records"
