# Repository notebooks render read-only

Notebook files selected from Home, the framework checkout, or another repository root must render as read-only documents through `/api/notebook`. Only notebooks whose path resolves inside the active workspace may receive Jupyter kernel controls. This lets ignored local examples appear under Recently updated and remain inspectable without weakening the workspace-scoped execution boundary.
