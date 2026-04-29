"""Model roundtrip tests — create, serialize, deserialize, verify."""

import pytest
from pydantic import ValidationError

from app.models import (
    Alert,
    AlertIOC,
    Automation,
    ExecConfig,
    InvestigationEdge,
    InvestigationNode,
    Playbook,
    PlaybookCondition,
    PlaybookEdge,
    PlaybookExecution,
    PlaybookNode,
    Position,
    Session,
    SessionSummary,
    ChatMessage,
    ToolCallMeta,
    DisplayData,
    ParamSchema,
    Skill,
    SkillInventory,
    BackgroundInvestigation,
    ResumeResult,
    SuccessResponse,
    AutomationSummary,
    ExecutionResult,
    NodeState,
)


# ---------------------------------------------------------------------------
# Session roundtrip
# ---------------------------------------------------------------------------


class TestSessionRoundtrip:
    def test_minimal_session(self):
        s = Session(id="s1", name="Test", created_at="2024-01-01", updated_at="2024-01-01")
        data = s.model_dump()
        restored = Session(**data)
        assert restored.id == "s1"
        assert restored.nodes == {}
        assert restored.edges == []
        assert restored.messages == []

    def test_session_with_nodes_and_edges(self):
        node = InvestigationNode(
            node_id="n1",
            action_type="query_execution",
            query="SELECT 1",
            result_summary="1 row",
            status="completed",
            confidence=0.85,
            label="Test query",
            tags=["SEV-2"],
        )
        edge = InvestigationEdge(id="e1", source="n1", target="n2")
        msg = ChatMessage(
            id="m1", role="user", content="hello", timestamp="2024-01-01T00:00:00Z"
        )
        s = Session(
            id="s1",
            name="Full Session",
            created_at="2024-01-01",
            updated_at="2024-01-02",
            nodes={"n1": node},
            edges=[edge],
            messages=[msg],
            skills_used=["skill-a"],
            tools_used=["trino"],
        )
        data = s.model_dump()
        restored = Session(**data)
        assert "n1" in restored.nodes
        assert restored.nodes["n1"].confidence == 0.85
        assert restored.edges[0].source == "n1"
        assert restored.messages[0].role == "user"

    def test_session_extra_fields_preserved(self):
        """Session has extra='allow' so unknown fields should be accepted."""
        s = Session(
            id="s1",
            name="Test",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            custom_field="hello",  # extra field
        )
        data = s.model_dump()
        assert data["custom_field"] == "hello"

    def test_session_summary(self):
        ss = SessionSummary(
            id="s1",
            name="Test",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            node_count=5,
            max_severity="high",
            max_confidence=0.92,
            completed_count=3,
            has_sev=True,
        )
        data = ss.model_dump()
        restored = SessionSummary(**data)
        assert restored.node_count == 5
        assert restored.has_sev is True


# ---------------------------------------------------------------------------
# InvestigationNode roundtrip
# ---------------------------------------------------------------------------


class TestInvestigationNodeRoundtrip:
    def test_full_node(self):
        node = InvestigationNode(
            node_id="n1",
            parent_ids=["n0"],
            action_type="mcp_tool_call",
            skill_name="reg-spike",
            tool_name="execute_trino_query",
            source_tool="captain",
            query="SELECT count(*) FROM events",
            parameters={"date": "2024-01-01"},
            result_summary="42 rows",
            result_raw='[{"count": 42}]',
            displays=[DisplayData(type="table", data="<table>...</table>")],
            confidence=0.73,
            timestamp="2024-01-01T00:00:00Z",
            duration_ms=1234.5,
            status="completed",
            investigator_notes="Looks suspicious",
            ipynb_cell_ref=3,
            reasoning="High volume from single IP",
            confidence_reasoning="Strong signal",
            confidence_override=False,
            is_dead_end=False,
            subtree_collapsed=False,
            label="IP analysis",
            tags=["SEV-3", "ato"],
            pinned=True,
        )
        data = node.model_dump()
        restored = InvestigationNode(**data)
        assert restored.node_id == "n1"
        assert restored.displays[0].type == "table"
        assert restored.tags == ["SEV-3", "ato"]
        assert restored.pinned is True

    def test_node_extra_fields(self):
        """InvestigationNode has extra='allow'."""
        node = InvestigationNode(
            node_id="n1",
            unknown_future_field=42,
        )
        assert node.model_dump()["unknown_future_field"] == 42

    def test_node_defaults(self):
        node = InvestigationNode(node_id="n1")
        assert node.action_type == "query_execution"
        assert node.status == "running"
        assert node.confidence == 0
        assert node.parent_ids == []


# ---------------------------------------------------------------------------
# Alert roundtrip
# ---------------------------------------------------------------------------


class TestAlertRoundtrip:
    def test_alert_with_iocs(self):
        alert = Alert(
            id="alert-1",
            title="Registration spike",
            description="527 registrations from ghksc.xyz",
            status="investigating",
            severity="high",
            source="iris",
            alert_type="registration_spike",
            iocs=[
                AlertIOC(type="domain", value="ghksc.xyz"),
                AlertIOC(type="ip", value="185.220.101.34"),
            ],
            tags=["auto-detected", "fake-accounts"],
            metadata={"wow_pct": 34.2},
        )
        data = alert.model_dump()
        restored = Alert(**data)
        assert len(restored.iocs) == 2
        assert restored.iocs[0].type == "domain"
        assert restored.metadata["wow_pct"] == 34.2

    def test_alert_extra_fields(self):
        """Alert has extra='allow'."""
        alert = Alert(
            id="a1",
            title="Test",
            future_field="yes",
        )
        assert alert.model_dump()["future_field"] == "yes"

    def test_alert_defaults(self):
        alert = Alert(id="a1", title="Test")
        assert alert.status == "new"
        assert alert.severity == "medium"
        assert alert.source == "manual"
        assert alert.iocs == []
        assert alert.tags == []


# ---------------------------------------------------------------------------
# Automation roundtrip
# ---------------------------------------------------------------------------


class TestAutomationRoundtrip:
    def test_automation_with_params(self):
        auto = Automation(
            id="auto-1",
            name="Query registrations",
            description="Count registrations by domain",
            category="registration",
            exec_type="trino_query",
            exec_body="SELECT domain, count(*) FROM events WHERE date = '{DATE}'",
            exec_config=ExecConfig(headless_account="register", timeout=30000),
            inputs=[
                ParamSchema(name="DATE", type="date", description="Query date", required=True),
            ],
            outputs=[
                ParamSchema(name="result", type="string", description="Query result"),
            ],
        )
        data = auto.model_dump()
        restored = Automation(**data)
        assert restored.exec_type == "trino_query"
        assert restored.exec_config.headless_account == "register"
        assert len(restored.inputs) == 1
        assert restored.inputs[0].name == "DATE"

    def test_automation_summary(self):
        s = AutomationSummary(
            id="auto-1",
            name="Test",
            exec_type="python_script",
            input_count=3,
        )
        data = s.model_dump()
        assert data["input_count"] == 3

    def test_execution_result(self):
        r = ExecutionResult(
            success=True,
            output={"rows": 42},
            duration_ms=500.0,
        )
        data = r.model_dump()
        restored = ExecutionResult(**data)
        assert restored.output["rows"] == 42


# ---------------------------------------------------------------------------
# Playbook roundtrip
# ---------------------------------------------------------------------------


class TestPlaybookRoundtrip:
    def test_playbook_with_nodes_and_edges(self):
        pb = Playbook(
            id="pb-1",
            name="Reg Spike Triage",
            description="Automated investigation",
            category="registration_spike",
            inputs=[
                ParamSchema(name="DATE", type="date", required=True),
            ],
            nodes=[
                PlaybookNode(
                    id="n1",
                    ref_id="reg-events",
                    ref_type="automation",
                    label="Email domains",
                    inputs={"DATE": "{{input.DATE}}"},
                    position=Position(x=250, y=0),
                ),
                PlaybookNode(
                    id="n2",
                    ref_id="",
                    ref_type="prompt",
                    label="Analyze",
                    body="Analyze the findings",
                    position=Position(x=250, y=150),
                ),
            ],
            edges=[
                PlaybookEdge(
                    id="e1",
                    source="n1",
                    target="n2",
                    conditions=[
                        PlaybookCondition(field="result.count", operator="gt", value=100),
                    ],
                ),
            ],
            entry_node_ids=["n1"],
            version=2,
        )
        data = pb.model_dump()
        restored = Playbook(**data)
        assert len(restored.nodes) == 2
        assert restored.nodes[0].position.x == 250
        assert restored.edges[0].conditions[0].operator == "gt"
        assert restored.entry_node_ids == ["n1"]

    def test_playbook_execution(self):
        pe = PlaybookExecution(
            id="exec-1",
            playbook_id="pb-1",
            session_id="s-1",
            status="completed",
            node_states={
                "n1": NodeState(status="completed", output={"count": 42}),
                "n2": NodeState(status="failed", error="timeout"),
            },
            started_at="2024-01-01T00:00:00Z",
            finished_at="2024-01-01T00:05:00Z",
        )
        data = pe.model_dump()
        restored = PlaybookExecution(**data)
        assert restored.node_states["n1"].status == "completed"
        assert restored.node_states["n2"].error == "timeout"


# ---------------------------------------------------------------------------
# Investigation models
# ---------------------------------------------------------------------------


class TestInvestigationModels:
    def test_background_investigation(self):
        bi = BackgroundInvestigation(
            id="inv-1",
            session_id="s-1",
            alert_id="a-1",
            status="running",
            started_at="2024-01-01T00:00:00Z",
            node_count=5,
        )
        data = bi.model_dump()
        restored = BackgroundInvestigation(**data)
        assert restored.status == "running"
        assert restored.node_count == 5

    def test_resume_result(self):
        rr = ResumeResult(ok=True, session_id="s-1", status="resumed", message="OK")
        assert rr.model_dump()["ok"] is True


# ---------------------------------------------------------------------------
# Skill models
# ---------------------------------------------------------------------------


class TestSkillModels:
    def test_skill(self):
        s = Skill(
            name="reg-spike",
            description="Registration spike investigation",
            allowed_tools=["execute_trino_query", "search_slack"],
            file_path="/skills/reg-spike/SKILL.md",
            category="investigation",
            area="reg-spike",
        )
        data = s.model_dump()
        restored = Skill(**data)
        assert len(restored.allowed_tools) == 2

    def test_skill_inventory(self):
        inv = SkillInventory(
            investigation=[
                Skill(name="a", description="d", file_path="f", category="investigation", area="a"),
            ],
            action=[
                Skill(name="b", description="d", file_path="f", category="action", area="b"),
            ],
        )
        data = inv.model_dump()
        restored = SkillInventory(**data)
        assert len(restored.investigation) == 1
        assert len(restored.action) == 1


# ---------------------------------------------------------------------------
# Misc models
# ---------------------------------------------------------------------------


class TestMiscModels:
    def test_success_response(self):
        r = SuccessResponse()
        assert r.ok is True
        data = r.model_dump()
        assert data == {"ok": True}

    def test_tool_call_meta(self):
        tc = ToolCallMeta(
            tool_name="execute_trino_query",
            server="captain",
            parameters={"sql": "SELECT 1"},
            duration_ms=123.4,
            success=True,
        )
        data = tc.model_dump()
        restored = ToolCallMeta(**data)
        assert restored.tool_name == "execute_trino_query"

    def test_chat_message_extra(self):
        """ChatMessage has extra='allow'."""
        msg = ChatMessage(
            id="m1",
            role="assistant",
            content="hello",
            timestamp="2024-01-01T00:00:00Z",
            custom_ui_field="test",
        )
        assert msg.model_dump()["custom_ui_field"] == "test"

    def test_investigation_edge_extra(self):
        """InvestigationEdge has extra='allow'."""
        edge = InvestigationEdge(
            id="e1",
            source="n1",
            target="n2",
            animated=True,
        )
        assert edge.model_dump()["animated"] is True


# ---------------------------------------------------------------------------
# Validation error tests
# ---------------------------------------------------------------------------


class TestValidationErrors:
    def test_invalid_action_type(self):
        with pytest.raises(ValidationError):
            InvestigationNode(node_id="n1", action_type="invalid_type")

    def test_invalid_alert_status(self):
        with pytest.raises(ValidationError):
            Alert(id="a1", title="T", status="unknown_status")

    def test_invalid_alert_severity(self):
        with pytest.raises(ValidationError):
            Alert(id="a1", title="T", severity="super_critical")

    def test_invalid_exec_type(self):
        with pytest.raises(ValidationError):
            Automation(id="a1", name="T", exec_type="invalid")

    def test_invalid_node_status(self):
        with pytest.raises(ValidationError):
            InvestigationNode(node_id="n1", status="banana")

    def test_invalid_edge_relation(self):
        with pytest.raises(ValidationError):
            InvestigationEdge(id="e1", source="s", target="t", relation="invalid")
