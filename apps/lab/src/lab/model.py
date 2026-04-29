from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelError(ValueError):
    """Raised when model validation fails."""


class ProjectStatus(str, Enum):
    active = "active"
    paused = "paused"
    done = "done"
    archived = "archived"


class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")
# Reserved pseudo-project ids (Cerebro, productivity self-view, ...). They
# bypass the regular id regex because they start with ``__`` to avoid
# colliding with any real project id a user would plausibly pick.
_PSEUDO_IDS = {"__cerebro__", "__self__"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Accept either a bare date (YYYY-MM-DD) or an ISO datetime with optional
# seconds / timezone offset. We normalize on write, but readers should be
# generous about what they accept so hand-written holds don't blow up.
_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)


def _parse_enum(enum_cls, value, *, field_name: str):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(e.value for e in enum_cls)
        raise ModelError(f"{field_name}: {value!r} is not one of: {allowed}")


def _parse_date(value, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ModelError(f"{field_name}: {value!r} is not YYYY-MM-DD")
    try:
        _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ModelError(f"{field_name}: invalid date ({exc})") from exc
    return value


def _parse_timestamp(value, *, field_name: str) -> str | None:
    """Validate a date or ISO-ish datetime string. Returns it unchanged.

    Accepts ``YYYY-MM-DD`` (dates) and ISO 8601 datetimes (``T`` or space
    separator, optional seconds/fractional/timezone). Callers that want a
    strict full timestamp should normalize before persisting.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not _TS_RE.match(value):
        raise ModelError(f"{field_name}: {value!r} is not a valid date/timestamp")
    return value


def _parse_hold(value, *, field_name: str = "hold") -> dict | None:
    """Validate the project ``hold`` dict (soft snooze metadata).

    Shape::

        {
          "until":  "YYYY-MM-DD" | "YYYY-MM-DDTHH:MM:SSZ",  # required
          "reason": "why this is parked",                    # optional
          "url":    "https://...",                           # optional
          "set_at": "YYYY-MM-DDTHH:MM:SSZ",                  # optional, stamped by writer
        }

    ``None`` / missing means no hold. Unknown keys are preserved so the UI
    can round-trip extensions without losing data.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ModelError(f"{field_name}: must be an object or null")
    until = value.get("until")
    if not until:
        raise ModelError(f"{field_name}.until: required")
    _parse_timestamp(until, field_name=f"{field_name}.until")
    set_at = value.get("set_at")
    if set_at is not None:
        _parse_timestamp(set_at, field_name=f"{field_name}.set_at")
    reason = value.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ModelError(f"{field_name}.reason: must be a string")
    url = value.get("url")
    if url is not None and not isinstance(url, str):
        raise ModelError(f"{field_name}.url: must be a string")
    return dict(value)


def _today() -> str:
    return _dt.date.today().isoformat()


def validate_id(value: str, *, field_name: str = "id") -> str:
    if isinstance(value, str) and value in _PSEUDO_IDS:
        return value
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ModelError(f"{field_name}: {value!r} must match [a-z0-9][a-z0-9\\-_]*")
    return value


# Kept for backward compatibility — earlier code imported `_validate_id`.
_validate_id = validate_id


@dataclass
class Project:
    id: str
    name: str
    status: ProjectStatus = ProjectStatus.active
    description: str = ""
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    priority: Priority | None = None
    loe: float | None = None
    due: str | None = None
    created: str = field(default_factory=_today)
    updated: str = field(default_factory=_today)
    worktrees: list[dict[str, Any]] = field(default_factory=list)
    prs: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    # External reference URLs used as project context (reading material,
    # slack threads, blog posts). Distinct from ``artifacts`` — artifacts
    # are canonical online mirrors of local work; references are inbound
    # source material. Shape: {id, url, title, note, added}.
    references: list[dict[str, Any]] = field(default_factory=list)
    pinned: list[str] = field(default_factory=list)
    hold: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        return cls(
            id=_validate_id(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            status=_parse_enum(ProjectStatus, data.get("status", "active"), field_name="status"),
            tags=list(data.get("tags", []) or []),
            labels=list(data.get("labels", []) or []),
            priority=_parse_enum(Priority, data.get("priority"), field_name="priority"),
            loe=(None if data.get("loe") is None else float(data["loe"])),
            due=_parse_date(data.get("due"), field_name="due"),
            created=_parse_date(data.get("created", _today()), field_name="created") or _today(),
            updated=_parse_date(data.get("updated", _today()), field_name="updated") or _today(),
            worktrees=list(data.get("worktrees", []) or []),
            prs=list(data.get("prs", []) or []),
            artifacts=list(data.get("artifacts", []) or []),
            references=list(data.get("references", []) or []),
            pinned=list(data.get("pinned", []) or []),
            hold=_parse_hold(data.get("hold")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "tags": list(self.tags),
            "labels": list(self.labels),
            "priority": self.priority.value if self.priority else None,
            "loe": self.loe,
            "due": self.due,
            "created": self.created,
            "updated": self.updated,
            "worktrees": list(self.worktrees),
            "prs": list(self.prs),
            "artifacts": list(self.artifacts),
            "references": list(self.references),
            "pinned": list(self.pinned),
            "hold": dict(self.hold) if self.hold else None,
        }


@dataclass
class Task:
    id: int
    title: str
    status: TaskStatus
    priority: Priority
    loe: float | None = None
    due: str | None = None
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    blocker: str | None = None
    notes_file: str | None = None
    created: str = field(default_factory=_today)
    updated: str = field(default_factory=_today)
    closed_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        task_id = data.get("id")
        if not isinstance(task_id, int) or task_id < 1:
            raise ModelError(f"id: {task_id!r} must be a positive integer")
        title = str(data.get("title", "")).strip()
        if not title:
            raise ModelError("title must be non-empty")
        status = _parse_enum(TaskStatus, data.get("status", "todo"), field_name="status")
        priority = _parse_enum(Priority, data.get("priority"), field_name="priority")
        if priority is None:
            raise ModelError("priority is required (P0..P3)")
        return cls(
            id=task_id,
            title=title,
            status=status,
            priority=priority,
            loe=(None if data.get("loe") is None else float(data["loe"])),
            due=_parse_date(data.get("due"), field_name="due"),
            tags=list(data.get("tags", []) or []),
            labels=list(data.get("labels", []) or []),
            blocker=(str(data["blocker"]) if data.get("blocker") else None),
            notes_file=(str(data["notes_file"]) if data.get("notes_file") else None),
            created=_parse_date(data.get("created", _today()), field_name="created") or _today(),
            updated=_parse_date(data.get("updated", _today()), field_name="updated") or _today(),
            closed_at=(str(data["closed_at"]) if data.get("closed_at") else None),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "priority": self.priority.value,
            "loe": self.loe,
            "due": self.due,
            "tags": list(self.tags),
            "labels": list(self.labels),
            "blocker": self.blocker,
            "notes_file": self.notes_file,
            "created": self.created,
            "updated": self.updated,
            "closed_at": self.closed_at,
        }
