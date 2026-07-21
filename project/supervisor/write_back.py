"""Helpers for post-approval write-back mode (dry-run vs live).

Resolution order for every setting: DB ``system_config`` → env var → default.
Admin UI writes to DB; env vars remain the fallback for fresh deployments.
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)


def _config_get(key: str) -> str | None:
    """Read from ``system_config`` via Persistence (import-safe)."""
    try:
        from persistence import Persistence
        return Persistence().config.get(key)
    except Exception:
        return None


def get_write_back_mode() -> str:
    """Return ``dry_run`` (default) or ``live`` from DB / ``WRITE_BACK_MODE``."""
    raw = (_config_get("write_back_mode") or os.getenv("WRITE_BACK_MODE") or "dry_run").strip().lower()
    if raw in {"live", "real"}:
        return "live"
    return "dry_run"


def is_live_write_back() -> bool:
    """True when side-effecting integrations may be called."""
    return get_write_back_mode() == "live"


def get_notify_owner_email() -> str | None:
    """Optional internal owner email for notifications (global default)."""
    value = (_config_get("notify_owner_email") or os.getenv("NOTIFY_OWNER_EMAIL") or "").strip()
    return value or None


def get_followup_notify_email() -> str | None:
    """Notify target for Automated Follow-Up.

    Resolution order:
    1. DB ``followup_notify_email`` / env ``FOLLOWUP_NOTIFY_EMAIL``
    2. DB ``notify_owner_email`` / env ``NOTIFY_OWNER_EMAIL``
    """
    specific = (_config_get("followup_notify_email") or os.getenv("FOLLOWUP_NOTIFY_EMAIL") or "").strip()
    if specific:
        return specific
    return get_notify_owner_email()


def get_followup_inactive_days() -> float:
    """Days of inactivity before a follow-up is recommended (default 7)."""
    raw = (os.getenv("FOLLOWUP_INACTIVE_DAYS") or "7").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 7.0


def get_followup_escalate_days() -> float:
    """Days of inactivity before escalation (default 14)."""
    raw = (os.getenv("FOLLOWUP_ESCALATE_DAYS") or "14").strip()
    try:
        value = max(0.0, float(raw))
    except ValueError:
        value = 14.0
    inactive = get_followup_inactive_days()
    return max(value, inactive)


def intake_check_existing_records_enabled() -> bool:
    """When true, Intake routing checks Monday for prior items from the same contact."""
    raw = (
        _config_get("intake_check_existing_records")
        or os.getenv("INTAKE_CHECK_EXISTING_RECORDS")
        or "true"
    ).strip().lower()
    return raw not in {"0", "false", "no", "off"}
