"""REST routes for the management overview dashboard."""

from fastapi import APIRouter

from backend.schemas import DashboardOverviewResponse
from supervisor.audit_log import get_dashboard_overview

router = APIRouter()


@router.get("/overview", response_model=DashboardOverviewResponse)
def read_dashboard_overview() -> DashboardOverviewResponse:
    """Return pending approvals and recent audit activity (no live agent runs)."""
    return DashboardOverviewResponse.model_validate(get_dashboard_overview())
