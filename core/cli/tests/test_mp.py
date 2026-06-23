from __future__ import annotations

from pathlib import Path

from lab import mp as mp_mod


def test_load_prefixes_has_seed_entries() -> None:
    p = mp_mod.load_prefixes()
    assert p.get("lipy-davi") == "davi"
    assert p.get("abuse-scoring-rules") == "drools"
    assert p.get("abuse-short-term-action") == "asta"
    assert p.get("im_playbooks") == "im"


def test_prefix_for() -> None:
    assert mp_mod.prefix_for("lipy-davi") == "davi"
    assert mp_mod.prefix_for("nonexistent") is None


def test_objective_from_known_prefix() -> None:
    assert mp_mod.objective_from("davi-great-vision") == "great-vision"
    assert mp_mod.objective_from("drools-rate-limit") == "rate-limit"


def test_objective_from_no_prefix() -> None:
    assert mp_mod.objective_from("oncall-drop-signups") == "oncall-drop-signups"


def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch) -> None:
    fake = tmp_path / "mp.json"
    monkeypatch.setattr(mp_mod, "_CONFIG_FILE", fake)
    mp_mod.save_prefixes({"foo": "bar"})
    assert mp_mod.load_prefixes() == {"foo": "bar"}
