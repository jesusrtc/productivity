from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ActionType = Literal[
    "skill_invocation",
    "mcp_tool_call",
    "query_execution",
    "enrichment",
    "annotation",
    "recommendation",
]

NodeStatus = Literal["running", "completed", "failed", "needs_review", "paused_for_input"]

EdgeRelation = Literal["led_to", "branched_from", "supports"]


class DisplayData(BaseModel):
    type: Literal["table", "json", "text", "html", "image"]
    data: str
    metadata: dict | None = None


class InvestigationNode(BaseModel):
    model_config = {"extra": "allow"}

    node_id: str
    parent_ids: list[str] = Field(default_factory=list)
    action_type: ActionType = "query_execution"
    skill_name: str | None = None
    tool_name: str | None = None
    source_tool: str | None = None
    query: str = ""
    parameters: dict = Field(default_factory=dict)
    result_summary: str = ""
    result_raw: str = ""
    displays: list[DisplayData] = Field(default_factory=list)
    confidence: float = 0
    timestamp: str = ""
    duration_ms: float = 0
    status: NodeStatus = "running"
    investigator_notes: str = ""
    ipynb_cell_ref: int | None = None
    reasoning: str = ""
    input_prompt: str | None = None
    input_choices: list[str] | None = None
    confidence_reasoning: str = ""
    confidence_override: bool = False
    is_dead_end: bool = False
    subtree_collapsed: bool = False
    label: str = ""
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False


class InvestigationEdge(BaseModel):
    model_config = {"extra": "allow"}

    id: str
    source: str
    target: str
    relation: EdgeRelation = "led_to"
