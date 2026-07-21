"""Business rules for deciding when human approval is required.

Resolution order: DB ``system_config`` → built-in defaults.
Admin UI writes ``approval_rules`` (JSON) and ``approval_confidence_threshold``.
"""

from __future__ import annotations

import json

from models.agent_result import AgentResult

# Built-in defaults used when DB has no override.
# Phase 3 agents (ai_mockup, installation_qc) are reserved stubs until built.
DEFAULT_RISKY_STATUS_MAP: dict[str, set[str]] = {
    "email_reply_monitoring": {"UNANSWERED"},
    "vendor_followup": {"SEND_REMINDER", "ESCALATE"},
    "po_automation": {"PO_READY_FOR_RELEASE"},
    "artwork_verification": {"MISMATCH", "UNCERTAIN"},
    "automated_followup": {"SEND_FOLLOWUP", "ESCALATE"},
    "storefront_search": {"FOUND", "LOW_CONFIDENCE", "SEARCH_FAILED"},
    "installer_matching": {"MATCHED", "LOW_CONFIDENCE"},
    # Phase 3 HITL stubs — Supervisor owns these gates when agents land.
    "ai_mockup": {"READY_FOR_EXTERNAL_SHARE", "LOW_CONFIDENCE"},
    "installation_qc": {"FAIL", "NEEDS_REVIEW", "LOW_CONFIDENCE"},
}

# Backwards-compatible alias for tests and docs.
RISKY_STATUS_MAP = DEFAULT_RISKY_STATUS_MAP

DEFAULT_CONFIDENCE_THRESHOLD = 0.75

KNOWN_APPROVAL_AGENTS = frozenset(DEFAULT_RISKY_STATUS_MAP.keys())


def _config_get(key: str) -> str | None:
    try:
        from persistence import Persistence

        return Persistence().config.get(key)
    except Exception:
        return None


def get_confidence_threshold() -> float:
    """Global confidence threshold below which approval is required."""
    raw = (_config_get("approval_confidence_threshold") or "").strip()
    if raw:
        try:
            value = float(raw)
            return max(0.0, min(1.0, value))
        except ValueError:
            pass
    return DEFAULT_CONFIDENCE_THRESHOLD


def get_risky_status_map() -> dict[str, set[str]]:
    """Per-agent risky statuses (DB override merged with defaults)."""
    raw = (_config_get("approval_rules") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                merged = {k: set(v) for k, v in DEFAULT_RISKY_STATUS_MAP.items()}
                for agent, statuses in parsed.items():
                    if agent in KNOWN_APPROVAL_AGENTS and isinstance(statuses, list):
                        merged[agent] = {
                            str(s).strip() for s in statuses if str(s).strip()
                        }
                return merged
        except (ValueError, TypeError, AttributeError):
            pass
    return {k: set(v) for k, v in DEFAULT_RISKY_STATUS_MAP.items()}


def get_risky_statuses(agent_name: str) -> set[str]:
    """Return the set of risky statuses for an agent."""
    return set(get_risky_status_map().get(agent_name, set()))


def requires_human_approval(agent_name: str, result: AgentResult) -> bool:
    """Determine whether a task result needs human approval."""
    risky_statuses = get_risky_statuses(agent_name)
    if risky_statuses:
        status = result.data.get("status")
        if status in risky_statuses:
            return True

    if result.confidence < get_confidence_threshold():
        return True

    return result.requires_approval


def serialize_risky_status_map(mapping: dict[str, set[str]]) -> str:
    """JSON payload for ``approval_rules`` config key."""
    payload = {agent: sorted(statuses) for agent, statuses in sorted(mapping.items())}
    return json.dumps(payload, separators=(",", ":"))


def parse_risky_status_map(raw: str) -> dict[str, set[str]]:
    """Parse and validate stored approval rules JSON."""
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("approval_rules must be a JSON object")
    result: dict[str, set[str]] = {}
    for agent, statuses in parsed.items():
        if agent not in KNOWN_APPROVAL_AGENTS:
            raise ValueError(f"unknown approval agent: {agent}")
        if not isinstance(statuses, list):
            raise ValueError(f"statuses for {agent} must be a list")
        result[agent] = {str(s).strip() for s in statuses if str(s).strip()}
    return result
