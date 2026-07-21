"""Admin configuration and operator management (admin role only)."""

from __future__ import annotations

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import Principal, require_roles
from persistence import Persistence
from supervisor.approval_policy import (
    get_confidence_threshold,
    get_risky_status_map,
    parse_risky_status_map,
    serialize_risky_status_map,
    KNOWN_APPROVAL_AGENTS,
)

router = APIRouter()
_admin = require_roles("admin")

INTAKE_CATEGORIES = (
    "new_project",
    "quote_request",
    "support_issue",
    "general_inquiry",
    "unclassified",
)


class OperatorAccount(BaseModel):
    email: str
    display_name: str | None
    role: str
    active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class OperatorUpdateRequest(BaseModel):
    role: str | None = None
    active: bool | None = None


class CategoryOwner(BaseModel):
    category: str
    email: str
    source: str


class ApprovalRule(BaseModel):
    agent_name: str
    risky_statuses: list[str]
    confidence_threshold: float


class ApprovalRuleUpdateRequest(BaseModel):
    risky_statuses: list[str]


class AdminConfigResponse(BaseModel):
    write_back_mode: str
    notify_owner_email: str
    followup_notify_email: str
    category_owners: list[CategoryOwner]
    approval_rules: list[ApprovalRule]


def _operator_row(row: dict) -> OperatorAccount:
    return OperatorAccount(
        email=row["email"],
        display_name=row.get("display_name"),
        role=row["role"],
        active=bool(row.get("active", True)),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_login_at=row.get("last_login_at"),
    )


class ConfigUpdateRequest(BaseModel):
    value: str


class ConfigEntry(BaseModel):
    key: str
    value: str
    source: str


class ConfigAuditEntry(BaseModel):
    id: str
    config_key: str
    old_value: str | None
    new_value: str
    changed_by: str
    changed_at: datetime


def _resolve_category_owner(category: str) -> tuple[str, str]:
    store = Persistence()
    db_key = f"intake_{category}_owner_email"
    db_val = (store.config.get(db_key) or "").strip()
    if db_val:
        return db_val, f"system_config:{db_key}"
    direct = (os.getenv(f"INTAKE_{category.upper()}_OWNER_EMAIL") or "").strip()
    if direct:
        return direct, f"INTAKE_{category.upper()}_OWNER_EMAIL"
    raw = (os.getenv("INTAKE_CATEGORY_OWNER_EMAILS") or "").strip()
    if raw:
        try:
            mapping = json.loads(raw)
            candidate = str(mapping.get(category) or "").strip()
            if candidate:
                return candidate, "INTAKE_CATEGORY_OWNER_EMAILS"
        except (ValueError, AttributeError):
            pass
    db_owner = (store.config.get("notify_owner_email") or "").strip()
    if db_owner:
        return db_owner, "system_config:notify_owner_email"
    fallback = (os.getenv("NOTIFY_OWNER_EMAIL") or "").strip()
    return fallback, "NOTIFY_OWNER_EMAIL"


@router.get("/operators", response_model=list[OperatorAccount])
def list_operators(
    _principal: Principal = Depends(_admin),
) -> list[OperatorAccount]:
    """List all operator accounts."""
    rows = Persistence().operators.list_all()
    return [_operator_row(row) for row in rows]


@router.patch("/operators/{email}", response_model=OperatorAccount)
def update_operator(
    email: str,
    payload: OperatorUpdateRequest,
    principal: Principal = Depends(_admin),
) -> OperatorAccount:
    """Update an operator role or active flag."""
    if payload.role is None and payload.active is None:
        raise HTTPException(status_code=400, detail="No fields to update")

    store = Persistence()
    existing = store.operators.get(email)
    if not existing:
        raise HTTPException(status_code=404, detail="Operator not found")

    normalized = existing["email"]
    if normalized == principal.email and payload.active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    if normalized == principal.email and payload.role and payload.role != "admin":
        raise HTTPException(status_code=400, detail="Cannot demote your own admin role")

    if payload.role is not None:
        try:
            updated = store.operators.set_role(normalized, payload.role)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="Operator not found")

    if payload.active is not None:
        if not store.operators.set_active(normalized, payload.active):
            raise HTTPException(status_code=404, detail="Operator not found")

    refreshed = store.operators.get(normalized)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Operator not found")
    return _operator_row(refreshed)


def _effective_value(key: str, env_name: str) -> str:
    store = Persistence()
    return (store.config.get(key) or os.getenv(env_name) or "").strip()


def _effective_write_back_mode() -> str:
    store = Persistence()
    raw = (store.config.get("write_back_mode") or os.getenv("WRITE_BACK_MODE") or "dry_run").strip().lower()
    return "live" if raw in {"live", "real"} else "dry_run"


@router.get("/config", response_model=AdminConfigResponse)
def read_config(
    _principal: Principal = Depends(_admin),
) -> AdminConfigResponse:
    """Read routing owners and approval policy (DB → env fallback)."""
    category_owners: list[CategoryOwner] = []
    for category in INTAKE_CATEGORIES:
        owner_email, source = _resolve_category_owner(category)
        category_owners.append(
            CategoryOwner(category=category, email=owner_email, source=source)
        )

    approval_rules = [
        ApprovalRule(
            agent_name=agent,
            risky_statuses=sorted(statuses),
            confidence_threshold=get_confidence_threshold(),
        )
        for agent, statuses in sorted(get_risky_status_map().items())
    ]

    return AdminConfigResponse(
        write_back_mode=_effective_write_back_mode(),
        notify_owner_email=_effective_value("notify_owner_email", "NOTIFY_OWNER_EMAIL"),
        followup_notify_email=_effective_value("followup_notify_email", "FOLLOWUP_NOTIFY_EMAIL"),
        category_owners=category_owners,
        approval_rules=approval_rules,
    )


def _validate_config_value(key: str, value: str) -> str:
    trimmed = value.strip()
    if key == "approval_confidence_threshold":
        try:
            threshold = float(trimmed)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Threshold must be a number") from exc
        if not 0.0 <= threshold <= 1.0:
            raise HTTPException(status_code=400, detail="Threshold must be between 0 and 1")
        return str(threshold)
    if key == "approval_rules":
        try:
            parsed = parse_risky_status_map(trimmed)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return serialize_risky_status_map(parsed)
    return trimmed


@router.put("/config/{key}", response_model=ConfigEntry)
def update_config(
    key: str,
    payload: ConfigUpdateRequest,
    principal: Principal = Depends(_admin),
) -> ConfigEntry:
    """Set a system config value. Changes are audited."""
    store = Persistence()
    try:
        validated = _validate_config_value(key, payload.value)
        saved = store.config.set(key, validated, changed_by=principal.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ConfigEntry(key=key, value=saved, source="system_config")


@router.put("/approval-rules/{agent_name}", response_model=ApprovalRule)
def update_approval_rule(
    agent_name: str,
    payload: ApprovalRuleUpdateRequest,
    principal: Principal = Depends(_admin),
) -> ApprovalRule:
    """Update risky statuses for one agent."""
    if agent_name not in KNOWN_APPROVAL_AGENTS:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")

    store = Persistence()
    current = get_risky_status_map()
    current[agent_name] = {s.strip() for s in payload.risky_statuses if s.strip()}
    serialized = serialize_risky_status_map(current)
    store.config.set("approval_rules", serialized, changed_by=principal.email)

    return ApprovalRule(
        agent_name=agent_name,
        risky_statuses=sorted(current[agent_name]),
        confidence_threshold=get_confidence_threshold(),
    )


@router.get("/config/audit", response_model=list[ConfigAuditEntry])
def config_audit_log(
    _principal: Principal = Depends(_admin),
) -> list[ConfigAuditEntry]:
    """Return recent config change history."""
    store = Persistence()
    return [ConfigAuditEntry(**row) for row in store.config.audit_log()]
