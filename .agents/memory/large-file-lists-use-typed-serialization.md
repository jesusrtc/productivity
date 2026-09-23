# Large file lists use typed generic response serialization

`/api/workspace-files` declares `list[dict[str, Any]]` so FastAPI/Pydantic can
serialize the result without the untyped Python `jsonable_encoder` traversal.
Keep the generic dictionary values: dates, pending state, symlink information,
and worktree annotations must survive without filtering or coercion.
`lab_file_scan_latency.py --transport asgi` compares full serialized responses
and includes validation/serialization, unlike its default direct-route mode.
Normal HTTP/browser probes are still required; this does not solve large DOM
rendering or demonstrate that every cold workspace open meets 200ms.
