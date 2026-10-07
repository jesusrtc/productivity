"""Workspace-owned command recipes. Reading or saving never runs commands."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from lab import storage
from pydantic import BaseModel, Field, field_validator

lock = threading.RLock()


class Step(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    cwd: str = Field(default="", max_length=4096)
    command: str = Field(min_length=1, max_length=16000)

    @field_validator("label", "cwd")
    @classmethod
    def clean_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("NUL characters are not allowed")
        return value.strip()

    @field_validator("label", "command")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Enter a terminal name and command")
        return value


class Automation(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    name: str = Field(min_length=1, max_length=120)
    steps: list[Step] = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or "\x00" in value:
            raise ValueError("Enter an automation name")
        return value


class Catalog(BaseModel):
    automations: list[Automation] = Field(default_factory=list, max_length=32)

    @field_validator("automations")
    @classmethod
    def unique_ids(cls, rows: list[Automation]) -> list[Automation]:
        if len({row.id for row in rows}) != len(rows):
            raise ValueError("Automation IDs must be unique")
        return rows


def read(folder: Path) -> dict:
    path = folder / ".lab" / "terminal-automations.json"
    raw = path.read_bytes() if path.is_file() else b""
    if len(raw) > 1024 * 1024:
        raise ValueError("Terminal automations exceed 1 MB")
    catalog = Catalog.model_validate_json(raw) if raw else Catalog()
    return {**catalog.model_dump(), "revision": hashlib.sha256(raw).hexdigest()}


def save(folder: Path, catalog: Catalog, revision: str) -> dict:
    with lock:
        if read(folder)["revision"] != revision:
            raise FileExistsError("Automations changed elsewhere. Reopen this section before saving.")
        data = {"automations": [row.model_dump() for row in catalog.automations]}
        if len(json.dumps(data).encode()) > 1024 * 1024:
            raise ValueError("Terminal automations exceed 1 MB")
        storage.write_json(folder / ".lab" / "terminal-automations.json", data)
        return read(folder)


def resolve_steps(automation: Automation, parent_cwd: Path) -> list[dict]:
    rows = []
    for step in automation.steps:
        path = Path(step.cwd).expanduser() if step.cwd else parent_cwd
        if not path.is_absolute():
            path = parent_cwd / path
        path = path.resolve()
        if not path.is_dir():
            raise ValueError(f"{step.label}: working directory does not exist: {path}")
        rows.append({**step.model_dump(), "cwd": str(path)})
    return rows


def shell_command(shell: str, cwd: Path, command: str) -> list[str]:
    """Run once before opening an interactive shell, preserving exited logs.

    Pass the user's program as one quoted shell argument, never as tmux input:
    startup timing, prompts and terminal control sequences cannot consume it.
    The outer POSIX shell survives `exit` in the user's command.
    """
    import shlex
    quote = shlex.quote
    program = f"cd {quote(str(cwd))} || exit\n{command}"
    wrapper = (f"{quote(shell)} -l -c {quote(program)}; "
               "lab_automation_status=$?; "
               "printf '\\n[Automation exited: %s]\\n' \"$lab_automation_status\"; "
               f"cd {quote(str(cwd))}; exec {quote(shell)} -l")
    return ["/bin/sh", "-c", wrapper]
