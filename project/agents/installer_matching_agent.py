"""Installer Matching agent — rank installers by region and capacity."""

from __future__ import annotations

from agents.base_agent import BaseAgent
from integrations.installer_matching import match_status, rank_installers
from models.agent_result import AgentResult
from models.task import InstallMatchRequest


class InstallerMatchingAgent(BaseAgent):
    """Recommend an installer for a project based on region and spare capacity."""

    def execute(self, task: InstallMatchRequest) -> AgentResult:
        project = task.project
        if project.assigned_installer.strip():
            return AgentResult(
                data={
                    "status": "ALREADY_ASSIGNED",
                    "project_id": project.project_id,
                    "project_name": project.project_name,
                    "install_region": project.install_region,
                    "install_date": project.install_date,
                    "monday_item_id": project.monday_item_id,
                    "assigned_installer": project.assigned_installer,
                },
                confidence=1.0,
                requires_approval=False,
                reasoning=(
                    f"Project '{project.project_name}' already has installer "
                    f"'{project.assigned_installer}' — no match needed."
                ),
            )

        region = str(project.install_region or "").strip()
        if not region:
            return AgentResult(
                data={
                    "status": "MISSING_REGION",
                    "project_id": project.project_id,
                    "project_name": project.project_name,
                    "install_region": "",
                    "install_date": project.install_date,
                    "monday_item_id": project.monday_item_id,
                },
                confidence=1.0,
                requires_approval=False,
                reasoning=(
                    f"Project '{project.project_name}' has no install region — "
                    "add a region before running Installer Matching."
                ),
            )

        ranked = rank_installers(region, task.installers)
        if not ranked:
            return AgentResult(
                data={
                    "status": "NO_MATCH",
                    "project_id": project.project_id,
                    "project_name": project.project_name,
                    "install_region": region,
                    "install_date": project.install_date,
                    "monday_item_id": project.monday_item_id,
                },
                confidence=0.9,
                requires_approval=False,
                reasoning=(
                    f"No installers with spare capacity found for region '{region}'. "
                    "Ops can assign manually or update the installer roster."
                ),
            )

        best = ranked[0]
        installer = best.installer
        status = match_status(best.confidence)
        return AgentResult(
            data={
                "status": status,
                "project_id": project.project_id,
                "project_name": project.project_name,
                "install_region": region,
                "install_date": project.install_date,
                "monday_item_id": project.monday_item_id,
                "recommended_installer": installer.name,
                "recommended_installer_id": installer.installer_id,
                "recommended_installer_email": installer.email,
                "recommended_installer_region": installer.region,
                "match_type": best.match_type,
                "available_capacity": best.available_capacity,
                "match_confidence": best.confidence,
            },
            confidence=best.confidence,
            requires_approval=status == "LOW_CONFIDENCE",
            reasoning=(
                f"Recommended '{installer.name}' for '{project.project_name}' "
                f"in {region} ({best.match_type.replace('_', ' ')}, "
                f"{best.available_capacity} open slot(s), "
                f"confidence {best.confidence:.0%})."
            ),
        )
