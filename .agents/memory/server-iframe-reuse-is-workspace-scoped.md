# Server iframe reuse is workspace-scoped

`openWorkspaceProxy` must match both the server name and the owning absolute
workspace path before reusing `proxyWrap` / `proxyIframe`. Server names such as
`app` repeat across workspaces; workspace names also repeat across vaults.
The old iframe remains in the shared content area during a warm workspace
switch, so checking only its server name displays the previous workspace's app.

Keep the iframe intact for repeated opens in the same workspace so watcher
refreshes and re-clicks preserve the embedded app's state. Regression coverage
is in `core/tests/test_frontend_workspace_proxy.py` for direct/proxied views,
return switches, and same-named workspaces across vaults.
