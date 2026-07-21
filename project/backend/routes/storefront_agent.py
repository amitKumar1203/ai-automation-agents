"""REST routes for the Storefront Search agent."""

from fastapi import APIRouter, HTTPException

from backend.schemas import StorefrontAnalysisSummaryResponse
from backend.services.agent_runs import run_storefront_batch
from integrations.monday_client import MondayConfigError, MondayFetchError

router = APIRouter()


@router.get("/run", response_model=StorefrontAnalysisSummaryResponse)
def run_storefront_agent() -> StorefrontAnalysisSummaryResponse:
    """Search storefront imagery for live Monday projects and log to audit."""
    try:
        summary = run_storefront_batch()
    except (MondayFetchError, MondayConfigError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return StorefrontAnalysisSummaryResponse.model_validate(summary)
