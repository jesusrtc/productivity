"""Upgrade saved browser links before authentication resolves their vault scope."""
from urllib.parse import parse_qsl, urlencode

from starlette.responses import RedirectResponse


def legacy_link_redirect(request):
    if request.url.path == "/":
        pairs = list(parse_qsl(request.url.query, keep_blank_values=True))
        query = dict(pairs)
        legacy = "project" in query or "assistant_project" in query or query.get("view") == "workspace"
        if legacy:
            renamed = []
            for key, value in pairs:
                key = {"workspace": "vault", "project": "workspace", "assistant_project": "assistant_workspace"}.get(key, key)
                if key == "view" and value == "workspace":
                    value = "vault"
                renamed.append((key, value))
            return RedirectResponse("/?" + urlencode(renamed), status_code=307)
    return None
