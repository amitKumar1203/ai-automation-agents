"""Tests for POAutomationAgent."""

from datetime import datetime, timedelta, timezone

from agents.po_automation_agent import POAutomationAgent
from models.task import ProjectApproval
from supervisor.approval_policy import requires_human_approval
from supervisor.supervisor import Supervisor

NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
AGENT = POAutomationAgent()


def _project(
    *,
    po_exists: bool,
    project_id: str = "PRJ-TEST",
    client_name: str = "Test Client",
    estimated_amount: float = 10000.0,
    vendor_name: str = "Test Vendor",
) -> ProjectApproval:
    return ProjectApproval(
        project_id=project_id,
        client_name=client_name,
        approved_at=NOW - timedelta(days=2),
        po_exists=po_exists,
        estimated_amount=estimated_amount,
        vendor_name=vendor_name,
    )


def test_po_already_exists() -> None:
    """When a PO already exists, status should be ALREADY_EXISTS."""
    task = _project(po_exists=True)

    result = AGENT.execute(task, current_time=NOW)

    assert result.data["status"] == "ALREADY_EXISTS"
    assert result.data["project_id"] == "PRJ-TEST"
    assert "draft_po" not in result.data
    assert result.confidence == 1.0
    assert result.requires_approval is False
    assert "already exists" in result.reasoning.lower()


def test_po_ready_for_release_includes_draft() -> None:
    """Missing PO should produce PO_READY_FOR_RELEASE with a draft payload."""
    task = _project(
        po_exists=False,
        project_id="PRJ-READY",
        client_name="Horizon Labs",
        estimated_amount=48250.50,
        vendor_name="Delta Components",
    )

    result = AGENT.execute(task, current_time=NOW)

    assert result.data["status"] == "PO_READY_FOR_RELEASE"
    assert result.confidence == 1.0
    assert result.requires_approval is True
    assert "draft_po" in result.data

    draft = result.data["draft_po"]
    assert draft["project_id"] == "PRJ-READY"
    assert draft["client_name"] == "Horizon Labs"
    assert draft["vendor_name"] == "Delta Components"
    assert draft["estimated_amount"] == 48250.50
    assert draft["generated_at"] == NOW.isoformat()
    assert "awaiting release approval" in result.reasoning.lower()


def test_po_ready_status_is_risky_in_approval_policy() -> None:
    """PO_READY_FOR_RELEASE must force approval via RISKY_STATUS_MAP."""
    result = AGENT.execute(_project(po_exists=False), current_time=NOW)
    assert requires_human_approval("po_automation", result) is True


def test_already_exists_does_not_force_via_status_map() -> None:
    """ALREADY_EXISTS is not a risky status and should not force approval."""
    result = AGENT.execute(_project(po_exists=True), current_time=NOW)
    assert requires_human_approval("po_automation", result) is False


def test_supervisor_batch_po_automation() -> None:
    """Supervisor batch should count approvals only for ready-for-release items."""
    supervisor = Supervisor()
    tasks = [
        _project(po_exists=True, project_id="PRJ-A"),
        _project(po_exists=False, project_id="PRJ-B"),
        _project(po_exists=False, project_id="PRJ-C"),
    ]

    summary = supervisor.run_batch(
        "po_automation",
        tasks,
        [task.project_id for task in tasks],
    )

    assert summary["total"] == 3
    assert summary["needs_approval_count"] == 2
    assert summary["auto_processed_count"] == 1
