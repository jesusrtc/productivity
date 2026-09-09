from __future__ import annotations

from pathlib import Path

from lab import mp as mp_mod


def test_load_prefixes_reads_configured_entries() -> None:
    p = mp_mod.load_prefixes()
    assert p.get("sample-charts") == "charts"
    assert p.get("sample-rules") == "rules"
    assert p.get("sample-service") == "service"
    assert p.get("sample-guides") == "im"


def test_prefix_for() -> None:
    assert mp_mod.prefix_for("sample-charts") == "charts"
    assert mp_mod.prefix_for("nonexistent") is None


def test_objective_from_known_prefix() -> None:
    assert mp_mod.objective_from("charts-great-vision") == "great-vision"
    assert mp_mod.objective_from("rules-rate-limit") == "rate-limit"


def test_objective_from_no_prefix() -> None:
    assert mp_mod.objective_from("oncall-drop-signups") == "oncall-drop-signups"


def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch) -> None:
    fake = tmp_path / "mp.json"
    monkeypatch.setattr(mp_mod, "_CONFIG_FILE", fake)
    mp_mod.save_prefixes({"foo": "bar"})
    assert mp_mod.load_prefixes() == {"foo": "bar"}


def test_shipped_prefix_config_is_empty():
    import json
    config = Path(mp_mod.__file__).parent / "config" / "mp-prefixes.json"
    assert json.loads(config.read_text()) == {}
