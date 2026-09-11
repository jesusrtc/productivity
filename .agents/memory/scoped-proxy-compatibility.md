# Scoped proxy compatibility

Proxy Referer rewriting and auth scope parsing must support `/api/vault-proxy/<vault>/<workspace>/<server>/` plus legacy `/api/workspace-proxy/...` and unscoped `/api/proxy/...` mounts. Exclude explicit HTTP/WS proxy URLs and shared `/api/log/` and `/api/appstate/` requests from rewriting. Preserve legacy HTTP and WebSocket aliases for cached apps. Vite base and React Router basename must agree with the canonical iframe URL; restoring asset aliases alone does not repair a mismatched router basename.

Regression coverage lives in `core/tests/test_proxy_routes.py`.
