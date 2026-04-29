from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .automation import ParamSchema


ConditionOperator = Literal["gt", "lt", "eq", "neq", "contains", "exists", "not_empty"]
RefType = Literal["automation", "playbook", "condition", "note", "prompt"]
ExecutionStatus = Literal["running", "completed", "failed", "cancelled"]
NodeStateStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class PlaybookCondition(BaseModel):
    field: str
    operator: ConditionOperator
    value: Any = None


class Position(BaseModel):
    x: float = 0
    y: float = 0


class PlaybookNode(BaseModel):
    id: str
    ref_id: str = ""
    ref_type: RefType = "automation"
    label: str = ""
    inputs: dict[str, str] = Field(default_factory=dict)
    input_refs: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    position: Position = Field(default_factory=Position)


class PlaybookEdge(BaseModel):
    id: str
    source: str
    target: str
    conditions: list[PlaybookCondition] | None = None
    label: str | None = None


class Playbook(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = ""
    inputs: list[ParamSchema] = Field(default_factory=list)
    nodes: list[PlaybookNode] = Field(default_factory=list)
    edges: list[PlaybookEdge] = Field(default_factory=list)
    entry_node_ids: list[str] = Field(default_factory=list)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class NodeState(BaseModel):
    status: NodeStateStatus = "pending"
    output: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class PlaybookExecution(BaseModel):
    id: str
    playbook_id: str
    session_id: str
    status: ExecutionStatus = "running"
    node_states: dict[str, NodeState] = Field(default_factory=dict)
    resolved_inputs: dict[str, Any] = Field(default_factory=dict)
    started_at: str = ""
    finished_at: str | None = None
