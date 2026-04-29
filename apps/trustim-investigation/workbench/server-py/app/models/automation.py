from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ExecType = Literal["trino_query", "davi_widget", "python_script", "claude_prompt"]
ParamType = Literal["string", "number", "date", "member_id_list", "boolean"]


class ParamSchema(BaseModel):
    name: str
    type: ParamType
    description: str = ""
    required: bool = False
    default: str | None = None


class ExecConfig(BaseModel):
    headless_account: str | None = None
    widget_name: str | None = None
    timeout: int | None = None


class Automation(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = ""
    exec_type: ExecType
    exec_body: str = ""
    exec_config: ExecConfig = Field(default_factory=ExecConfig)
    inputs: list[ParamSchema] = Field(default_factory=list)
    outputs: list[ParamSchema] = Field(default_factory=list)
    source_skill: str | None = None
    created_at: str = ""
    updated_at: str = ""


class AutomationSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = ""
    exec_type: ExecType
    input_count: int = 0
    source_skill: str | None = None


class DisplayItem(BaseModel):
    type: str
    data: str


class ExecutionResult(BaseModel):
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0
    displays: list[DisplayItem] | None = None
