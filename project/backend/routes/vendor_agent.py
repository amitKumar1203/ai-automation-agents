"""REST routes for the Vendor Follow-Up Agent."""

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import VendorAnalysisSummaryResponse
from backend.services.agent_runs import run_vendor_batch
from integrations.monday_client import MondayConfigError, MondayFetchError

router = APIRouter()


@router.get("/run", response_model=VendorAnalysisSummaryResponse)
def run_vendor_agent(
    source: str = Query(
        default="monday",
        pattern="^(mock|monday)$",
        description="Data source: monday (default) or mock (tests/CI)",
    ),
) -> VendorAnalysisSummaryResponse:
    """Run the vendor follow-up agent via the Supervisor on mock or live Monday.com requests."""
    try:
        summary = run_vendor_batch(use_real_monday=(source == "monday"))
    except (MondayFetchError, MondayConfigError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return VendorAnalysisSummaryResponse.model_validate(summary)
