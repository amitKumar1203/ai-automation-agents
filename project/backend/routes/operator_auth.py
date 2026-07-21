"""Internal operator provisioning used by the authenticated frontend."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from persistence import Persistence

router = APIRouter()


class OperatorLoginRequest(BaseModel):
    email: str
    name: str | None = None


class OperatorResponse(BaseModel):
    email: str
    name: str | None
    role: str


@router.post("/operator", response_model=OperatorResponse)
def ensure_operator(payload: OperatorLoginRequest) -> OperatorResponse:
    """Create an operator on first login and return its persisted role."""
    default_role = (os.getenv("AUTH_DEFAULT_ROLE") or "operator").strip().lower()
    try:
        account = Persistence().operators.ensure(
            str(payload.email),
            display_name=payload.name,
            default_role=default_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not bool(account["active"]):
        raise HTTPException(status_code=403, detail="Operator account is disabled")
    return OperatorResponse(
        email=account["email"],
        name=account["display_name"],
        role=account["role"],
    )
