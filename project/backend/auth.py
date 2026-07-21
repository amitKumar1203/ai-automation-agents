"""API authentication helpers for agent routes, webhooks, and cron."""

from __future__ import annotations

import os
import secrets
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, Header, HTTPException


def _expected_api_key() -> str:
    return (os.getenv("API_KEY") or "").strip()


def _expected_cron_secret() -> str:
    return (os.getenv("CRON_SECRET") or os.getenv("API_KEY") or "").strip()


def _constant_time_equal(provided: str, expected: str) -> bool:
    """Compare secrets without early-exit on length mismatch."""
    try:
        return secrets.compare_digest(provided, expected)
    except (TypeError, ValueError):
        return False


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Require ``X-API-Key`` matching ``API_KEY`` (constant-time compare).

    When ``API_KEY`` is unset (local pytest), the check is skipped so unit
    tests do not need secrets. Production must set ``API_KEY``.
    """
    expected = _expected_api_key()
    if not expected:
        if _production():
            raise HTTPException(status_code=503, detail="API key is not configured")
        return
    provided = (x_api_key or "").strip()
    if not provided or not _constant_time_equal(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_cron_secret(
    authorization: Annotated[str | None, Header()] = None,
    x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Require cron/webhook secret via Bearer, X-Cron-Secret, or X-API-Key."""
    expected = _expected_cron_secret()
    if not expected:
        if _production():
            raise HTTPException(
                status_code=503, detail="Cron secret is not configured"
            )
        return

    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()

    provided = (x_cron_secret or bearer or x_api_key or "").strip()
    if not provided or not _constant_time_equal(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@dataclass(frozen=True)
class Principal:
    email: str
    role: str


def _production() -> bool:
    return (
        (os.getenv("ENVIRONMENT") or "").lower() == "production"
        or (os.getenv("NODE_ENV") or "").lower() == "production"
        or bool(os.getenv("VERCEL"))
    )


def _identity_message(timestamp: str, email: str, role: str) -> bytes:
    return f"{timestamp}\n{email}\n{role}".encode("utf-8")


def sign_trusted_identity(
    secret: str,
    *,
    timestamp: str,
    email: str,
    role: str,
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        _identity_message(timestamp, email.lower(), role),
        hashlib.sha256,
    ).hexdigest()


def require_trusted_principal(
    x_principal_email: Annotated[
        str | None, Header(alias="X-Principal-Email")
    ] = None,
    x_principal_role: Annotated[
        str | None, Header(alias="X-Principal-Role")
    ] = None,
    x_principal_timestamp: Annotated[
        str | None, Header(alias="X-Principal-Timestamp")
    ] = None,
    x_principal_signature: Annotated[
        str | None, Header(alias="X-Principal-Signature")
    ] = None,
) -> Principal:
    """Authenticate a short-lived identity assertion from the frontend BFF."""
    secret = (os.getenv("TRUSTED_IDENTITY_SECRET") or "").strip()
    if not secret:
        if _production():
            raise HTTPException(
                status_code=503, detail="Trusted identity is not configured"
            )
        return Principal(email="local@localhost", role="admin")

    email = (x_principal_email or "").strip().lower()
    role = (x_principal_role or "").strip().lower()
    timestamp = (x_principal_timestamp or "").strip()
    signature = (x_principal_signature or "").strip().removeprefix("sha256=")
    if not email or role not in {"operator", "reviewer", "admin"}:
        raise HTTPException(status_code=401, detail="Invalid trusted principal")
    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid principal timestamp") from exc
    window = int(os.getenv("TRUSTED_IDENTITY_WINDOW_SECONDS", "60"))
    if abs(time.time() - sent_at) > window:
        raise HTTPException(status_code=401, detail="Principal assertion expired")

    expected = sign_trusted_identity(
        secret,
        timestamp=timestamp,
        email=email,
        role=role,
    )
    if not _constant_time_equal(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid principal signature")
    return Principal(email=email, role=role)


def require_roles(*roles: str) -> Callable[..., Principal]:
    """Build a reusable FastAPI dependency requiring one of the given roles."""
    allowed = frozenset(roles)
    invalid = allowed - {"operator", "reviewer", "admin"}
    if not allowed or invalid:
        raise ValueError(f"invalid required roles: {sorted(invalid)}")

    def dependency(
        principal: Annotated[Principal, Depends(require_trusted_principal)],
    ) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return principal

    return dependency
