"""API contract tests — verify response shapes match frontend expectations."""

import json

import pytest


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_shape(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert isinstance(data["uptime"], (int, float))
    assert isinstance(data["sessions"], int)
    assert "timestamp" in data
    assert "bridge" in data


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sessions_list_shape(client):
    r = await client.get("/api/sessions")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_sessions_list_item_fields(client, tmp_path):
    """When a session exists, the summary should have the expected fields."""
    from app.config import settings

    session = {
        "id": "test-sess-1",
        "name": "Test Session",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "nodes": {
            "n1": {
                "node_id": "n1",
                "status": "completed",
                "confidence": 0.8,
                "tags": ["SEV-2"],
            }
        },
        "edges": [],
        "messages": [],
    }
    fp = settings.sessions_dir / "test-sess-1.json"
    fp.write_text(json.dumps(session))

    r = await client.get("/api/sessions")
    data = r.json()
    assert len(data) >= 1
    item = data[0]
    required_fields = {"id", "name", "created_at", "updated_at", "node_count", "max_severity"}
    assert required_fields.issubset(item.keys()), (
        f"Missing fields: {required_fields - item.keys()}"
    )
    assert item["node_count"] == 1
    assert item["max_severity"] == "SEV-2"


@pytest.mark.asyncio
async def test_session_crud(client):
    """PUT, GET, DELETE a session."""
    session_data = {
        "id": "crud-test",
        "name": "CRUD Test",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "nodes": {},
        "edges": [],
        "messages": [],
    }
    # Create
    r = await client.put("/api/sessions/crud-test", content=json.dumps(session_data))
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Read
    r = await client.get("/api/sessions/crud-test")
    assert r.status_code == 200
    assert r.json()["id"] == "crud-test"

    # Delete
    r = await client.delete("/api/sessions/crud-test")
    assert r.status_code == 200

    # Verify gone
    r = await client.get("/api/sessions/crud-test")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skills_shape(client):
    r = await client.get("/api/skills")
    assert r.status_code == 200
    data = r.json()
    assert "investigation" in data
    assert "action" in data
    assert isinstance(data["investigation"], list)
    assert isinstance(data["action"], list)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerts_list_empty(client):
    r = await client.get("/api/alerts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_alert_create_and_read(client):
    body = {
        "id": "test-alert-1",
        "title": "Test Alert",
        "description": "A test alert",
        "severity": "high",
        "source": "manual",
        "iocs": [{"type": "ip", "value": "1.2.3.4"}],
    }
    r = await client.post("/api/alerts", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "test-alert-1"
    assert data["title"] == "Test Alert"
    assert data["severity"] == "high"
    assert "created_at" in data
    assert "updated_at" in data
    assert len(data["iocs"]) == 1

    # Verify it appears in list
    r = await client.get("/api/alerts")
    alerts = r.json()
    assert len(alerts) == 1
    assert alerts[0]["id"] == "test-alert-1"
    # Summary fields
    assert "session_count" in alerts[0]
    assert "ioc_count" in alerts[0]


@pytest.mark.asyncio
async def test_alert_patch(client):
    body = {"id": "patch-alert", "title": "Original"}
    await client.post("/api/alerts", json=body)
    r = await client.patch("/api/alerts/patch-alert", json={"title": "Updated"})
    assert r.status_code == 200
    assert r.json()["title"] == "Updated"


@pytest.mark.asyncio
async def test_alert_delete(client):
    await client.post("/api/alerts", json={"id": "del-alert", "title": "Delete Me"})
    r = await client.delete("/api/alerts/del-alert")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_alert_sync_stubs(client):
    """Sync endpoints should return structured responses (even as stubs)."""
    r = await client.get("/api/alerts/sync/status")
    assert r.status_code == 200
    assert "running" in r.json()

    r = await client.post("/api/alerts/sync")
    assert r.status_code == 200
    assert "new_alerts" in r.json()


# ---------------------------------------------------------------------------
# Automations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_automations_list(client):
    r = await client.get("/api/automations")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # DAVI widgets are always present
    davi_ids = [a["id"] for a in data if a["id"].startswith("davi-")]
    assert len(davi_ids) >= 1  # At least some DAVI widgets


@pytest.mark.asyncio
async def test_automation_create(client):
    body = {
        "id": "custom-test",
        "name": "Custom Query",
        "exec_type": "trino_query",
        "exec_body": "SELECT 1",
    }
    r = await client.post("/api/automations", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "id" in data
    assert data["name"] == "Custom Query"


@pytest.mark.asyncio
async def test_automation_summary_fields(client):
    """AutomationSummary should include input_count."""
    body = {
        "id": "summ-test",
        "name": "Parameterized",
        "exec_type": "python_script",
        "inputs": [{"name": "X", "type": "string"}],
    }
    await client.post("/api/automations", json=body)
    r = await client.get("/api/automations")
    customs = [a for a in r.json() if a["name"] == "Parameterized"]
    assert len(customs) == 1
    assert customs[0]["input_count"] == 1


# ---------------------------------------------------------------------------
# Playbooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_playbooks_list(client):
    r = await client.get("/api/playbooks")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_playbook_create_and_read(client):
    body = {
        "name": "Test Playbook",
        "description": "For testing",
        "nodes": [
            {"id": "n1", "ref_type": "prompt", "label": "Step 1", "position": {"x": 0, "y": 0}},
        ],
        "edges": [],
    }
    r = await client.post("/api/playbooks", json=body)
    assert r.status_code == 200
    data = r.json()
    pb_id = data["id"]
    assert pb_id.startswith("pb-")
    assert data["version"] == 1
    assert data["entry_node_ids"] == ["n1"]

    # Read it back
    r = await client.get(f"/api/playbooks/{pb_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Test Playbook"


@pytest.mark.asyncio
async def test_playbook_executions_list(client):
    r = await client.get("/api/playbook-executions")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# Seed Demo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_demo(client):
    r = await client.post("/api/seed-demo")
    assert r.status_code == 200
    data = r.json()
    assert "seeded" in data
    assert isinstance(data["seeded"], dict)
    assert data["seeded"]["alerts"] >= 1
    assert data["seeded"]["playbooks"] >= 1

    # Calling again should not re-seed (files already exist)
    r2 = await client.post("/api/seed-demo")
    data2 = r2.json()
    assert data2["seeded"]["alerts"] == 0
    assert data2["seeded"]["playbooks"] == 0


# ---------------------------------------------------------------------------
# Investigations (stubs)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_investigations_list(client):
    r = await client.get("/api/investigations")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_investigation_start(client):
    body = {"sessionId": "s-1", "prompt": "Investigate alert 12345"}
    r = await client.post("/api/investigations/start", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "s-1"
    assert data["status"] == "running"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_templates_crud(client):
    r = await client.get("/api/templates")
    assert r.status_code == 200
    assert r.json() == []

    # Create
    r = await client.post("/api/templates", json={"name": "Test Template"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    tpl_id = r.json()["id"]

    # List
    r = await client.get("/api/templates")
    assert len(r.json()) == 1

    # Delete
    r = await client.delete(f"/api/templates/{tpl_id}")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# IOCs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iocs_crud(client):
    # Empty list
    r = await client.get("/api/iocs")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 0
    assert data["iocs"] == []

    # Add
    r = await client.post("/api/iocs", json={
        "sessionId": "s-1",
        "iocs": [{"type": "ip", "value": "1.2.3.4"}],
    })
    assert r.status_code == 200
    assert r.json()["added"] == 1

    # Check
    r = await client.get("/api/iocs/check", params={"value": "1.2.3.4"})
    assert r.status_code == 200
    assert r.json()["found"] is True


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queries_list(client):
    r = await client.get("/api/queries")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_all(client):
    r = await client.get("/api/export/all")
    assert r.status_code == 200
    data = r.json()
    assert "exported_at" in data
    assert "session_count" in data
    assert isinstance(data["sessions"], list)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tools(client):
    r = await client.get("/api/mcp/tools")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
