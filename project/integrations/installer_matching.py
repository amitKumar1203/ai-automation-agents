"""Rule-based installer ranking by region and available capacity."""

from __future__ import annotations

from dataclasses import dataclass

from models.task import InstallerProfile

_LOW_CONFIDENCE_THRESHOLD = 0.80


@dataclass(frozen=True)
class InstallerMatchResult:
    installer: InstallerProfile
    confidence: float
    match_type: str
    available_capacity: int


def normalize_region(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _regions_overlap(project_region: str, installer_region: str) -> bool:
    if not project_region or not installer_region:
        return False
    if project_region == installer_region:
        return True
    return project_region in installer_region or installer_region in project_region


def rank_installers(
    project_region: str,
    installers: list[InstallerProfile],
) -> list[InstallerMatchResult]:
    """Return installers ranked by region fit and spare capacity."""
    region = normalize_region(project_region)
    ranked: list[InstallerMatchResult] = []

    for installer in installers:
        capacity = max(int(installer.capacity or 0), 0)
        active = max(int(installer.active_jobs or 0), 0)
        available = capacity - active
        if available <= 0:
            continue

        installer_region = normalize_region(installer.region)
        capacity_ratio = min(available / max(capacity, 1), 1.0)

        if region and installer_region == region:
            confidence = 0.88 + (capacity_ratio * 0.1)
            match_type = "exact_region"
        elif region and _regions_overlap(region, installer_region):
            confidence = 0.72 + (capacity_ratio * 0.06)
            match_type = "partial_region"
        elif region:
            confidence = 0.55 + (capacity_ratio * 0.05)
            match_type = "fallback_region"
        else:
            confidence = 0.5
            match_type = "no_project_region"

        ranked.append(
            InstallerMatchResult(
                installer=installer,
                confidence=min(confidence, 0.98),
                match_type=match_type,
                available_capacity=available,
            )
        )

    ranked.sort(
        key=lambda item: (item.confidence, item.available_capacity),
        reverse=True,
    )
    return ranked


def match_status(confidence: float) -> str:
    if confidence >= _LOW_CONFIDENCE_THRESHOLD:
        return "MATCHED"
    return "LOW_CONFIDENCE"
