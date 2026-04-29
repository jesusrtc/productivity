from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab.storage import read_json, write_json


def test_write_json_creates_file_atomically(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    write_json(target, {"hello": "world"})
    assert target.is_file()
    assert json.loads(target.read_text()) == {"hello": "world"}


def test_write_json_is_atomic_no_temp_leftovers(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    write_json(target, {"x": 1})
    siblings = list(tmp_path.iterdir())
    assert siblings == [target], f"unexpected files: {siblings}"


def test_read_json_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    write_json(target, {"a": [1, 2, 3], "b": {"c": "d"}})
    assert read_json(target) == {"a": [1, 2, 3], "b": {"c": "d"}}


def test_read_json_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_json(tmp_path / "nope.json")


def test_write_json_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "out.json"
    write_json(target, {})
    assert target.is_file()


def test_write_json_cleans_up_temp_on_failure(tmp_path: Path) -> None:
    """A non-serializable payload raises and leaves no temp file behind."""
    class Unserializable:
        pass

    target = tmp_path / "out.json"
    with pytest.raises(TypeError):
        write_json(target, {"bad": Unserializable()})

    siblings = list(tmp_path.iterdir())
    assert siblings == [], f"unexpected files: {siblings}"
    assert not target.exists()
