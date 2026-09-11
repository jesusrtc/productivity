# Workspace creation needs only a name

The new-workspace form asks only for a human-facing name. The selected vault is
shown as context and stays captured when the form opens. Do not reintroduce
description, priority, due date, tags, labels, or a technical ID field.

The API accepts a name, generates a safe unique folder ID in the selected vault,
and creates the workspace through `lab workspace new --name`. Existing ID-based
API/CLI callers remain compatible.

The + picker replaces its contents when New workspace opens the vault choices.
Its outside-click handler must use the click's original `composedPath()` because
the clicked button is detached before the event reaches the document.
