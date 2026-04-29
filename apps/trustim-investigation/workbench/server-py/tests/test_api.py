import json

import pytest


# Note: client fixture and data dir isolation are provided by conftest.py


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_has_required_fields(client):
    r = await client.get("/api/health")
    data = r.json()
    for field in ("uptime", "sessions", "timestamp"):
        assert field in data, f"missing field: {field}"


@pytest.mark.asyncio
async def test_sessions_list(client):
    r = await client.get("/api/sessions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_skills_list(client):
    r = await client.get("/api/skills")
    assert r.status_code == 200
    data = r.json()
    assert "investigation" in data
    assert "action" in data


@pytest.mark.asyncio
async def test_skills_have_names(client):
    r = await client.get("/api/skills")
    data = r.json()
    for category in ("investigation", "action"):
        for skill in data[category]:
            assert "name" in skill and skill["name"]
            assert "category" in skill and skill["category"] == category


# ---------------------------------------------------------------------------
# Alerts endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerts_list(client):
    r = await client.get("/api/alerts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_alerts_create(client):
    r = await client.post("/api/alerts", json={
        "id": "a1",
        "title": "Test",
        "severity": "high",
    })
    assert r.status_code == 200
    assert r.json()["severity"] == "high"


@pytest.mark.asyncio
async def test_alerts_filter_by_severity(client):
    await client.post("/api/alerts", json={"id": "lo", "title": "Low", "severity": "low"})
    await client.post("/api/alerts", json={"id": "hi", "title": "High", "severity": "high"})
    r = await client.get("/api/alerts", params={"severity": "high"})
    data = r.json()
    assert all(a["severity"] == "high" for a in data)


# ---------------------------------------------------------------------------
# Automations endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_automations_list(client):
    r = await client.get("/api/automations")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_automations_create_and_delete(client):
    r = await client.post("/api/automations", json={
        "id": "cust-1",
        "name": "My Script",
        "exec_type": "python_script",
        "exec_body": "print(1)",
    })
    assert r.status_code == 200
    auto_id = r.json()["id"]

    r = await client.delete(f"/api/automations/{auto_id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ---------------------------------------------------------------------------
# Playbooks endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_playbooks_list(client):
    r = await client.get("/api/playbooks")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_playbooks_create(client):
    r = await client.post("/api/playbooks", json={
        "name": "Test PB",
        "nodes": [{"id": "n1", "ref_type": "prompt", "label": "Step", "position": {"x": 0, "y": 0}}],
        "edges": [],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Test PB"
    assert data["version"] == 1


# ---------------------------------------------------------------------------
# Seed demo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_demo(client):
    r = await client.post("/api/seed-demo")
    assert r.status_code == 200
    data = r.json()
    assert "seeded" in data
    assert data["seeded"]["alerts"] >= 1


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_save_and_get(client):
    session = {
        "id": "s-api-test",
        "name": "API Test",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "nodes": {},
        "edges": [],
        "messages": [],
    }
    r = await client.put("/api/sessions/s-api-test", content=json.dumps(session))
    assert r.status_code == 200

    r = await client.get("/api/sessions/s-api-test")
    assert r.status_code == 200
    assert r.json()["name"] == "API Test"


@pytest.mark.asyncio
async def test_session_not_found(client):
    r = await client.get("/api/sessions/nonexistent")
    assert r.status_code == 404
