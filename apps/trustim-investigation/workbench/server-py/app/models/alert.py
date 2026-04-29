from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AlertStatus = Literal["new", "investigating", "resolved", "dismissed"]
AlertSeverity = Literal["critical", "high", "medium", "low", "info"]
AlertSource = Literal["inresponse", "iris", "manual", "playbook", "external"]
IOCType = Literal["ip", "domain", "member_id", "email", "device_hash", "user_agent", "other"]


class AlertIOC(BaseModel):
    type: IOCType
    value: str


class Alert(BaseModel):
    model_config = {"extra": "allow"}

    id: str
    external_id: str | None = None
    title: str
    description: str = ""
    status: AlertStatus = "new"
    severity: AlertSeverity = "medium"
    source: AlertSource = "manual"
    alert_type: str = ""
    assignee: str | None = None
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str | None = None
    session_ids: list[str] = Field(default_factory=list)
    related_alert_ids: list[str] = Field(default_factory=list)
    iocs: list[AlertIOC] = Field(default_factory=list)
    suggested_playbook_id: str | None = None
    incident_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class AlertSummary(BaseModel):
    id: str
    external_id: str | None = None
    title: str
    status: AlertStatus
    severity: AlertSeverity
    source: AlertSource
    alert_type: str = ""
    assignee: str | None = None
    created_at: str = ""
    updated_at: str = ""
    session_count: int = 0
    ioc_count: int = 0
    related_count: int = 0
    tags: list[str] = Field(default_factory=list)


class AlertFilters(BaseModel):
    status: list[AlertStatus] | None = None
    severity: list[AlertSeverity] | None = None
    source: list[AlertSource] | None = None
    alert_type: str | None = None
    assignee: str | None = None
    search: str | None = None
    date_from: str | None = None
    date_to: str | None = None
