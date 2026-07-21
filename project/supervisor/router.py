"""Supervisor event router — evaluate incoming events and route to agents.

Maps webhook/cron event sources to specialised agent poll job types.
Callers enqueue work via the agent job worker; they do not invoke agents
directly for automated triggers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RouteTarget:
    """One agent poll to enqueue after an event is evaluated."""

    event_source: str
    job_type: str
    agent_name: str
    use_live: bool = True


# Event source → specialised agent(s). Artwork stays on-demand (no poll).
_EVENT_ROUTES: dict[str, tuple[RouteTarget, ...]] = {
    "gmail": (
        RouteTarget("gmail", "poll_email", "email_reply_monitoring"),
    ),
    "monday": (
        RouteTarget("monday", "poll_vendor", "vendor_followup"),
        RouteTarget("monday", "poll_storefront", "storefront_search"),
        RouteTarget("monday", "poll_installer", "installer_matching"),
    ),
    "salesforce": (
        RouteTarget("salesforce", "poll_po", "po_automation"),
        RouteTarget("salesforce", "poll_followup", "automated_followup"),
    ),
    "followup": (
        RouteTarget("followup", "poll_followup", "automated_followup"),
    ),
    "storefront": (
        RouteTarget("storefront", "poll_storefront", "storefront_search"),
    ),
    "installer": (
        RouteTarget("installer", "poll_installer", "installer_matching"),
    ),
}

_ALL_SOURCES = ("gmail", "monday", "salesforce", "followup", "storefront", "installer")


def known_event_sources() -> tuple[str, ...]:
    """Return supported event source names."""
    return tuple(sorted(_EVENT_ROUTES)) + ("all",)


def route_event(event_source: str) -> list[RouteTarget]:
    """Evaluate an incoming event and return agent route targets.

    Args:
        event_source: Webhook/cron source key (e.g. ``gmail``, ``all``).

    Returns:
        Ordered list of ``RouteTarget`` entries for the Supervisor queue.

    Raises:
        ValueError: If ``event_source`` is unknown.
    """
    key = (event_source or "").strip().lower()
    if key == "all":
        targets: list[RouteTarget] = []
        seen: set[str] = set()
        for source in _ALL_SOURCES:
            for target in _EVENT_ROUTES[source]:
                if target.job_type in seen:
                    continue
                seen.add(target.job_type)
                targets.append(target)
        return targets

    if key not in _EVENT_ROUTES:
        known = ", ".join(sorted(known_event_sources()))
        raise ValueError(f"Unknown event source '{event_source}'. Known: {known}")
    return list(_EVENT_ROUTES[key])


def route_event_job_types(event_source: str) -> list[str]:
    """Convenience: job types only for an event source."""
    return [t.job_type for t in route_event(event_source)]


def iter_poll_job_types() -> Iterable[str]:
    """All distinct poll job types the Supervisor queue may run."""
    seen: set[str] = set()
    for targets in _EVENT_ROUTES.values():
        for target in targets:
            if target.job_type not in seen:
                seen.add(target.job_type)
                yield target.job_type
