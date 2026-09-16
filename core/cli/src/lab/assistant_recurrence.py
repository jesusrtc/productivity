"""Explicit, idempotent advancement of agent-managed recurring tasks."""
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

from lab import assistant as db, assistant_records as records, assistant_documents as documents
from lab.assistant_meetings import safe_path, validate_date, write_record


def advance(root: Path, task_id: str) -> Path:
    source, metadata, _body = db.find_task(root, task_id)
    safe_path(root, source)
    status = records.progress_map(list(records.records(root)))[records.key(metadata)]["status"] if documents.enabled(root) else metadata.get("status")
    if status != "done":
        raise ValueError("complete the current task before creating its next occurrence")
    frequency = metadata.get("recurrence")
    if frequency not in {"weekly", "monthly", "yearly"}:
        raise ValueError("recurrence must be weekly, monthly, or yearly")
    try:
        due = date.fromisoformat(validate_date(metadata.get("due")))
        anchor = date.fromisoformat(validate_date(metadata.get("recurrence_anchor") or metadata.get("due")))
    except ValueError as exc:
        raise ValueError("confirm a valid due date before advancing recurrence") from exc
    if frequency == "weekly":
        following = due + timedelta(days=7)
    else:
        year, month = (due.year + 1, due.month) if frequency == "yearly" else (due.year + due.month // 12, due.month % 12 + 1)
        following = date(year, month, min(anchor.day, monthrange(year, month)[1]))
    series = str(metadata.get("recurrence_root") or task_id)
    identifier = f"{series}-{following.isoformat()}"
    db.validate_id(identifier)
    target = safe_path(root, source.parent / f"{identifier}.md")
    if target.exists():
        existing, _ = db.read_markdown(target)
        if existing.get("previous_task") != task_id or existing.get("due") != following.isoformat():
            raise ValueError("next occurrence path already belongs to a different task")
        return target
    fields = {key: metadata[key] for key in ("title", "workspace", "priority", "owner", "group", "tags", "source", "recurrence") if key in metadata}
    fields.update(id=identifier, status="ready", due=following.isoformat(), recurrence_anchor=anchor.isoformat(),
                  recurrence_root=series, previous_task=task_id, created=db.now_iso(), updated=db.now_iso())
    if records.enabled(root):
        fields.update({key: metadata.get(key) for key in ('project','workspace','parent')})
        fields.pop('id')
        title = fields.pop('title')
        return records.create(root, 'task', title, identifier=identifier, **fields,
                              body='')
    write_record(target, fields, "")
    return target
