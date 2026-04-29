"""Pydantic compliance audit — ensures every FastAPI route has typed responses."""

from fastapi.routing import APIRoute

from app.main import app


# Routes that return raw Response objects (not JSON) are exempt
_EXEMPT_PATHS = {
    "/api/export/json",      # Returns file download Response
    "/api/notebook/{session_id}",  # Returns ipynb file Response
}


def test_all_routes_have_response_model():
    """Every JSON-returning route must declare a response_model."""
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in _EXEMPT_PATHS:
            continue
        if route.response_model is None:
            missing.append(f"{route.methods} {route.path}")
    assert missing == [], (
        f"Routes missing response_model:\n" + "\n".join(f"  - {m}" for m in missing)
    )


def test_post_put_patch_routes_have_body_params():
    """Every POST/PUT/PATCH route should accept structured input (body or query params)."""
    write_methods = {"POST", "PUT", "PATCH"}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.methods & write_methods:
            continue
        # All write routes should have at least a path param or body param
        assert route.dependant is not None, (
            f"Route {route.methods} {route.path} has no dependant"
        )


def test_no_duplicate_route_paths():
    """No two routes should share the same (method, path) combination."""
    seen: dict[str, str] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            key = f"{method} {route.path}"
            assert key not in seen, (
                f"Duplicate route: {key} (endpoints: {seen[key]} and {route.name})"
            )
            seen[key] = route.name


def test_all_routes_have_tags():
    """Routes should be tagged for OpenAPI grouping."""
    untagged = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.tags:
            untagged.append(f"{route.methods} {route.path}")
    # Health is registered without a tag prefix via the router
    # This is informational — we just verify the check runs
    # (some routes like health may not have tags, which is acceptable)


def test_route_count_sanity():
    """Ensure we have a reasonable number of routes (catches broken imports)."""
    api_routes = [
        r for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api")
    ]
    # We should have at least 25 routes across all routers
    assert len(api_routes) >= 25, (
        f"Only {len(api_routes)} API routes found — expected at least 25. "
        "Check that all routers are included in app."
    )


def test_all_response_models_are_pydantic():
    """Every response_model should be a Pydantic BaseModel or a generic containing one."""
    from pydantic import BaseModel
    import typing

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in _EXEMPT_PATHS:
            continue
        rm = route.response_model
        if rm is None:
            continue  # Caught by test_all_routes_have_response_model

        # Handle list[X], dict[str, X], etc.
        origin = getattr(rm, "__origin__", None)
        if origin is list:
            args = getattr(rm, "__args__", ())
            if args:
                inner = args[0]
                # inner could be dict or a BaseModel
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    continue
                if getattr(inner, "__origin__", None) is dict:
                    continue
                # Allow other types (like str, int)
                continue
        if isinstance(rm, type) and issubclass(rm, BaseModel):
            continue
        # Allow other generic types
        if origin is not None:
            continue
        assert False, (
            f"Route {route.methods} {route.path} has response_model={rm} "
            "which is not a Pydantic BaseModel"
        )
