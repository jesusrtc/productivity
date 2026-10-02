# Link rows infer services from URLs

Folder/worktree links show locally bundled brand icons for common services,
including Google Workspace, Slack, Jira, Confluence, GitHub, and Grafana. Match
the actual URL hostname and Google/Atlassian path before legacy saved type names;
internal Assistant documents keep their own document glyph and target identity.

The metadata editor uses one collapsed line per saved link. Clicking the row
opens its name and destination fields. External link types are inferred from
the URL without a dropdown or prior Settings configuration; a separate Internal
document action retains the searchable whole-document/tab picker. Preserve
untouched custom types, revision checks, and unsaved edits on failed saves.

`core/src/core/static/link-services.json` is shared by the browser and backend.
Bundle new icons locally rather than fetching third-party favicons at runtime.
