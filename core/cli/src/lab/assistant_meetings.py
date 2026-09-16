"""Markdown meeting records; originals and derived documents have distinct paths."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

from lab import assistant as db, naming, assistant_records as records

logger = logging.getLogger(__name__)


def safe_path(root: Path, source: Path) -> Path:
    try:
        relative = source.relative_to(root)
    except ValueError as exc:
        raise ValueError("meeting path escapes Assistant database") from exc
    if ".." in relative.parts or not relative.parts:
        raise ValueError("invalid meeting path")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("meeting paths must not contain symlinks")
    if root.resolve() not in source.resolve().parents:
        raise ValueError("meeting path escapes Assistant database")
    return source


def workspace(root: Path, workspace_id: str) -> Path:
    directory = safe_path(root, db.workspace_dir(root, workspace_id))
    if not safe_path(root, naming.workspace_document_file(directory)).is_file():
        raise ValueError(f"Assistant workspace {workspace_id!r} not found")
    return directory


def validate_owner(source: Path, metadata: dict) -> None:
    if metadata.get('schema') == 2:
        if metadata.get('id') != source.stem or metadata.get('type') != 'note':
            raise ValueError('Invalid note identity')
        return
    if str(metadata.get("id") or source.stem) != source.stem:
        raise ValueError("meeting id does not match its path")
    if str(metadata.get("workspace") or source.parent.parent.name) != source.parent.parent.name:
        raise ValueError("meeting workspace does not match its path")


def validate_date(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("meeting date must be a valid YYYY-MM-DD date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("meeting date must be a valid YYYY-MM-DD date") from exc
    return value


def sort_key(row: dict) -> tuple:
    try:
        day = validate_date(row.get("date"))
    except ValueError:
        day = "0001-01-01"
    return (-date.fromisoformat(day).toordinal(), str(row.get("id") or ""), str(row.get("path") or ""))


def lines(body: str):
    fence = None
    for line in body.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", text)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            yield line, None, False
            continue
        if marker and (marker[1][0] != "`" or "`" not in marker[2]):
            fence = marker[1]
            yield line, None, False
            continue
        heading = re.match(r"^ {0,3}#(?:[ \t]+(.*))?$", text)
        title = re.sub(r"[ \t]+#+\s*$", "", heading[1] or "").strip().lower() if heading else None
        yield line, title, not text.startswith(("    ", "\t"))


def sections(body: str) -> tuple[str, str]:
    overview, notes = [], []
    section = None
    for line, heading, _visible in lines(body):
        if heading is not None:
            section = heading
        (overview if section in {"summary", "highlights", "action items"} else notes).append(line)
    supporting = "".join(notes)
    return "".join(overview), supporting if supporting.strip() else ""


def summary(body: str, tldr=None) -> str:
    section, content = None, []
    for line, heading, visible in lines(body):
        if heading is not None:
            section = heading
        elif section == "summary" and visible and line.strip() and not line.strip().startswith(("#", "![")):
            content.append(line.strip().removeprefix("- "))
    result = " ".join(content) or str(tldr or "")
    return result[:180].rstrip() + ("…" if len(result) > 180 else "")


def actions(body: str, *, all_sections: bool = False) -> list[dict]:
    section, content = None, []
    for line, heading, visible in lines(body):
        if heading is not None:
            section = heading
        if visible and (all_sections or section == "action items"):
            content.append(line)
    return db.extract_subtasks("".join(content))


def read_utf8(source: Path) -> bytes:
    try:
        data = source.expanduser().read_bytes()
        data.decode("utf-8")
        return data
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot import UTF-8 file: {exc}") from exc


def write_new(source: Path, data: bytes) -> None:
    missing, parent = [], source.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    created = False
    try:
        source.parent.mkdir(parents=True, exist_ok=True)
        with source.open("xb") as output:
            created = True
            output.write(data)
    except OSError as exc:
        if created:
            source.unlink()
        for directory in missing:
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        raise ValueError(f"cannot create meeting document: {exc}") from exc


def write_record(source: Path, metadata: dict, body: str) -> None:
    header = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items())
    write_new(source, f"---\n{header}\n---\n\n{body}".encode("utf-8"))


def validate_title(title) -> None:
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must not be empty")


def iter_series(root: Path, workspaces=None):
    if records.enabled(root):
        yield from records.note_rows(root, 'series')
        return
    for item in workspaces if workspaces is not None else db.iter_workspaces(root):
        for source in sorted((db.workspace_dir(root, item["id"]) / "meeting-series").glob("*.md")):
            try:
                safe_path(root, source)
                workspace(root, item["id"])
                metadata, body = db.read_markdown(source)
                validate_owner(source, metadata)
            except (ValueError, OSError) as exc:
                logger.warning("Skipping series %s: %s", source, exc)
                continue
            yield {**metadata, "id": source.stem, "workspace": item["id"],
                   "title": str(metadata.get("title") or source.stem), "workspace_name": item.get("name"),
                   "path": str(source.relative_to(root)), "body": body, "summary": summary(body, metadata.get("tldr"))}


def find_series(root: Path, series_id: str, workspace_id=None):
    if records.enabled(root):
        return records.resolve(root, series_id, 'meeting-series')
    db.validate_id(series_id)
    matches = [row for row in iter_series(root) if row["id"] == series_id
               and (workspace_id is None or row["workspace"] == workspace_id)]
    if not matches:
        raise ValueError(f"meeting series {series_id!r} not found")
    if len(matches) > 1:
        raise ValueError("meeting series is not unique; specify --workspace")
    source = root / matches[0]["path"]
    return source, *db.read_markdown(source)


def create_series(root: Path, series_id: str, *, workspace_id: str, title: str) -> Path:
    if records.enabled(root):
        return records.create(root, 'note', title, identifier=series_id, workspace=workspace_id,
                              note_type='series', body='')
    db.validate_id(series_id)
    validate_title(title)
    source = safe_path(root, workspace(root, workspace_id) / "meeting-series" / f"{series_id}.md")
    write_record(source, {"id": series_id, "title": title, "workspace": workspace_id,
                         "created": db.now_iso(), "updated": db.now_iso()}, "")
    return source


def find_meeting(root: Path, meeting_id: str):
    if records.enabled(root):
        return records.resolve(root, meeting_id, 'meetings')
    db.validate_id(meeting_id)
    matches = []
    for source in naming.workspaces_dir(root).glob(f"*/meetings/{meeting_id}.md"):
        safe_path(root, source)
        workspace(root, source.parent.parent.name)
        metadata, body = db.read_markdown(source)
        validate_owner(source, metadata)
        matches.append((source, metadata, body))
    if len(matches) != 1:
        raise ValueError(f"meeting {meeting_id!r} not found or not unique")
    return matches[0]


def raw_path(root: Path, source: Path) -> Path:
    if records.enabled(root):
        return records.raw_path(root, source)
    return safe_path(root, source.with_suffix("") / "raw.txt")


def resolve_content(root: Path, relative: str):
    if records.enabled(root):
        return records.resolve_content(root, relative)
    rel = Path(relative)
    p = rel.parts
    if rel.is_absolute() or ".." in p or len(p) not in {5, 6}:
        raise ValueError("invalid meeting content path")
    if p[0] != naming.workspaces_dir(root).name or p[2] != "meetings":
        raise ValueError("invalid meeting content path")
    raw = len(p) == 5 and p[4] == "raw.txt"
    kind = {"questions": "question", "documents": "document"}.get(p[4])
    if not raw and (len(p) != 6 or not kind or rel.suffix != ".md"):
        raise ValueError("invalid meeting content path")
    source = safe_path(root, root / rel)
    meeting = safe_path(root, root / Path(*p[:3]) / f"{p[3]}.md")
    workspace(root, p[1])
    if not source.is_file() or not meeting.is_file():
        raise FileNotFoundError("meeting or content not found")
    validate_owner(meeting, db.read_markdown(meeting)[0])
    metadata = {"title": "Raw notes", "kind": "raw"} if raw else db.read_markdown(source)[0]
    if not raw and (metadata.get("id") != source.stem or metadata.get("workspace") != p[1]
                    or metadata.get("meeting") != p[3] or metadata.get("kind") != kind):
        raise ValueError("meeting content ownership does not match its path")
    return source, meeting, metadata


def iter_contents(root: Path, meeting: Path):
    if records.enabled(root):
        yield from records.contents(root, meeting)
        return
    companion = safe_path(root, meeting.with_suffix(""))
    for kind in ("questions", "documents"):
        try:
            directory = safe_path(root, companion / kind)
        except ValueError as exc:
            logger.warning("Skipping meeting content: %s", exc)
            continue
        for source in sorted(directory.glob("*.md")):
            try:
                _, _, metadata = resolve_content(root, str(source.relative_to(root)))
            except (ValueError, OSError) as exc:
                logger.warning("Skipping meeting content %s: %s", source, exc)
                continue
            yield {"path": str(source.relative_to(root)), "id": source.stem,
                   "title": str(metadata.get("title") or source.stem), "kind": metadata["kind"]}


def iter_meetings(root: Path, workspaces=None):
    if records.enabled(root):
        yield from records.note_rows(root, 'meeting')
        return
    workspaces = list(workspaces if workspaces is not None else db.iter_workspaces(root))
    series = {(s["workspace"], s["id"]): s for s in iter_series(root, workspaces)}
    for item in workspaces:
        for source in sorted((db.workspace_dir(root, item["id"]) / "meetings").glob("*.md")):
            try:
                safe_path(root, source)
                metadata, body = db.read_markdown(source)
                validate_owner(source, metadata)
            except (ValueError, OSError) as exc:
                logger.warning("Skipping meeting %s: %s", source, exc)
                continue
            parent = series.get((item["id"], str(metadata.get("series") or "")), {})
            followups = actions(body)
            try:
                has_raw = raw_path(root, source).is_file()
            except ValueError:
                has_raw = False
            try:
                contents = list(iter_contents(root, source))
            except ValueError:
                contents = []
            yield {**metadata, "id": source.stem, "title": str(metadata.get("title") or source.stem),
                   "workspace": item["id"], "workspace_name": item.get("name"), "vault": item.get("vault"),
                   "vault_path": item.get("vault_path"), "workspace_path": item.get("workspace_path"),
                   "series": str(metadata.get("series") or "") or None,
                   "path": str(source.relative_to(root)), "mtime": source.stat().st_mtime, "body": body,
                   "summary": summary(body, metadata.get("tldr")), "series_title": parent.get("title"),
                   "series_path": parent.get("path"), "has_raw": has_raw, "content_count": len(contents),
                   "action_items": followups, "action_items_total": len(followups),
                   "action_items_done": sum(a["status"] == "done" for a in followups)}


def list_rows(root: Path, workspaces=None):
    return sorted([{k: v for k, v in row.items() if k != "body"}
                   for row in iter_meetings(root, workspaces)], key=sort_key)


def create_meeting(root: Path, title: str, *, workspace_id: str, date=None, undated=False,
                   attendees=None, tags=None, series=None, raw_file=None) -> Path:
    if records.enabled(root):
        validate_title(title)
        if undated and date is not None:
            raise ValueError('Choose --date or --undated, not both')
        day = None if undated else validate_date(date or datetime.now().astimezone().date().isoformat())
        raw = read_utf8(raw_file) if raw_file is not None else None
        source = records.create(root, 'note', title, note_type='meeting', workspace=workspace_id,
                                date=day, attendees=attendees or [], tags=tags or [], series=series,
                                body='')
        if raw is not None:
            try:
                write_new(raw_path(root, source), raw)
            except ValueError:
                source.unlink()
                raise
        return source
    directory = workspace(root, workspace_id)
    validate_title(title)
    if undated and date is not None:
        raise ValueError("choose --date or --undated, not both")
    day = None if undated else validate_date(date if date is not None else datetime.now().astimezone().date().isoformat())
    if series is not None:
        find_series(root, series, workspace_id)
    raw = read_utf8(raw_file) if raw_file is not None else None
    base = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + db.slugify(title)
    identifier, suffix = base, 2
    source = safe_path(root, directory / "meetings" / f"{identifier}.md")
    while source.exists() or source.is_symlink() or source.with_suffix("").exists() or source.with_suffix("").is_symlink():
        identifier, suffix = f"{base}-{suffix}", suffix + 1
        source = directory / "meetings" / f"{identifier}.md"
    target = raw_path(root, source)
    write_record(source, {"id": identifier, "title": title, "workspace": workspace_id,
                         "date": day, "attendees": attendees or [], "tags": tags or [], "series": series,
                         "created": db.now_iso(), "updated": db.now_iso()}, "")
    if raw is not None:
        try:
            write_new(target, raw)
        except ValueError:
            source.unlink()
            raise
    return source


def update_meeting(root: Path, meeting_id: str, field: str, value) -> Path:
    if records.enabled(root):
        if field not in {'title','date','series','tldr','workspace','project'}:
            raise ValueError('Unsupported note property')
        return records.update(root, meeting_id, field, value, collection='meetings')
    if field not in {"title", "date", "series", "tldr"}:
        raise ValueError("meeting field must be title, date, series, or tldr")
    source, metadata, body = find_meeting(root, meeting_id)
    if field == "title":
        validate_title(value)
    if field == "date" and value is not None:
        validate_date(value)
    if field == "series" and value is not None:
        find_series(root, value, source.parent.parent.name)
    metadata.update({field: value, "updated": db.now_iso()})
    db.write_markdown(source, metadata, body)
    return source


def add_raw(root: Path, meeting_id: str, file: Path) -> Path:
    meeting, _, _ = find_meeting(root, meeting_id)
    data = read_utf8(file)
    target = raw_path(root, meeting)
    if target.exists():
        raise ValueError("original raw notes already exist; they cannot be overwritten")
    write_new(target, data)
    return target


def create_content(root: Path, title: str, *, meeting_id: str, kind: str, file=None, url=None) -> Path:
    validate_title(title)
    if kind not in {"question", "document"}:
        raise ValueError("content kind must be question or document")
    meeting, _, _ = find_meeting(root, meeting_id)
    body = read_utf8(file).decode("utf-8") if file is not None else ""
    if url is not None:
        try:
            parsed = urlsplit(url)
            if parsed.scheme.lower() not in {"https", "http"} or not parsed.hostname or any(ord(c) <= 32 or ord(c) == 127 for c in url):
                raise ValueError
            parsed.port
        except ValueError as exc:
            raise ValueError("meeting content URL must be an absolute http(s) URL") from exc
        label = re.sub(r"([\\`*_\[\]<>!()])", r"\\\1", " ".join(title.split()))
        body += "\n\n[" + label + "](" + quote(url, safe=":/?#[]@!$&'*+,;=%") + ")\n"
    if records.enabled(root):
        metadata, _ = db.read_markdown(meeting)
        return records.create(root, 'note', title, note_type=kind, body=body,
                              parent={'type':'note','id':metadata['id']},
                              workspace=metadata.get('workspace'), project=metadata.get('project'))
    folders = [safe_path(root, meeting.with_suffix("") / name) for name in ("questions", "documents")]
    base = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + db.slugify(title)
    identifier, suffix = base, 2
    while any((folder / f"{identifier}.md").exists() or (folder / f"{identifier}.md").is_symlink() for folder in folders):
        identifier, suffix = f"{base}-{suffix}", suffix + 1
    source = folders[kind == "document"] / f"{identifier}.md"
    write_record(source, {"id": identifier, "title": title, "kind": kind, "meeting": meeting_id,
                         "workspace": meeting.parent.parent.name, "created": db.now_iso(), "updated": db.now_iso()}, body)
    return source
