"""Tests for Installer Matching agent."""

from agents.installer_matching_agent import InstallerMatchingAgent
from models.task import InstallMatchRequest, InstallProject, InstallerProfile


def test_installer_already_assigned() -> None:
    agent = InstallerMatchingAgent()
    result = agent.execute(
        InstallMatchRequest(
            project=InstallProject(
                project_id="P1",
                project_name="Done",
                install_region="Austin, TX",
                assigned_installer="Existing Co",
            ),
            installers=[],
        )
    )
    assert result.data["status"] == "ALREADY_ASSIGNED"


def test_installer_matched() -> None:
    agent = InstallerMatchingAgent()
    roster = [
        InstallerProfile(
            installer_id="1",
            name="Austin Signs",
            region="Austin, TX",
            capacity=5,
            active_jobs=1,
            email="ops@example.com",
        )
    ]
    result = agent.execute(
        InstallMatchRequest(
            project=InstallProject(
                project_id="P2",
                project_name="Lobby",
                install_region="Austin, TX",
            ),
            installers=roster,
        )
    )
    assert result.data["status"] == "MATCHED"
    assert result.data["recommended_installer"] == "Austin Signs"
