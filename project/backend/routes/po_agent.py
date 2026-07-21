"""REST routes for the Purchase Order Automation Agent."""

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import POAnalysisSummaryResponse
from backend.services.agent_runs import run_po_batch
from integrations.salesforce_client import (
    SalesforceAuthError,
    SalesforceConfigError,
    SalesforceFetchError,
)

router = APIRouter()


@router.get("/run", response_model=POAnalysisSummaryResponse)
def run_po_agent(
    source: str = Query(
        default="salesforce",
        pattern="^(mock|salesforce)$",
        description="Data source: salesforce (default) or mock (tests/CI)",
    ),
) -> POAnalysisSummaryResponse:
    """Run the PO automation agent via the Supervisor on mock or live Salesforce projects."""
    try:
        summary = run_po_batch(use_real_salesforce=(source == "salesforce"))
    except (SalesforceFetchError, SalesforceAuthError, SalesforceConfigError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return POAnalysisSummaryResponse.model_validate(summary)
