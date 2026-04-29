from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .node import InvestigationNode, InvestigationEdge


MessageRole = Literal["user", "assistant", "system"]

StartingInputType = Literal[
    "alert_id", "incident_id", "ioc", "natural_language", "raw_data", "none"
]


class ToolCallMeta(BaseModel):
    tool_name: str
    server: str
    parameters: dict = Field(default_factory=dict)
    duration_ms: float = 0
    success: bool = True


class SkillInvocationMeta(BaseModel):
    skill_name: str
    instructions_loaded: bool = False


class ChatMessage(BaseModel):
    model_config = {"extra": "allow"}

    id: str
    role: MessageRole
    content: str
    timestamp: str
    node_ids: list[str] = Field(default_factory=list)
    tool_call: ToolCallMeta | None = None
    skill_invocation: SkillInvocationMeta | None = None


class McpToolStatus(BaseModel):
    name: str
    server: str
    status: Literal["healthy", "degraded", "disconnected"] = "healthy"
    last_checked: str = ""


class Session(BaseModel):
    """Full session — matches the TypeScript Session interface exactly."""
    model_config = {"extra": "allow"}

    id: str
    name: str
    created_at: str
    updated_at: str
    starting_input: str = ""
    starting_input_type: StartingInputType = "none"
    nodes: dict[str, InvestigationNode] = Field(default_factory=dict)
    edges: list[InvestigationEdge] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    mcp_tools: list[McpToolStatus] = Field(default_factory=list)
    linked_sessions: list[str] | None = None


class SessionSummary(BaseModel):
    """Lightweight session metadata for listings."""
    id: str
    name: str
    created_at: str
    updated_at: str
    node_count: int
    max_severity: str
    max_confidence: float = 0
    completed_count: int = 0
    has_sev: bool = False
    skills_used: list[str] = Field(default_factory=list)
    starting_input_type: str = "none"
