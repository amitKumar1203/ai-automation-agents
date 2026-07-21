"""REST routes for the Automated Follow-Up Agent."""

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import FollowUpAnalysisSummaryResponse
from backend.services.agent_runs import run_followup_batch
from integrations.salesforce_client import (
    SalesforceAuthError,
    SalesforceConfigError,
    SalesforceFetchError,
)

router = APIRouter()


@router.get("/run", response_model=FollowUpAnalysisSummaryResponse)
def run_followup_agent(
    source: str = Query(
        default="salesforce",
        pattern="^(salesforce)$",
        description="Live Salesforce Approved_Project__c only (no mock)",
    ),
) -> FollowUpAnalysisSummaryResponse:
    """Run Automated Follow-Up on live Salesforce projects."""
    try:
        summary = run_followup_batch(use_real_salesforce=True)
    except (SalesforceFetchError, SalesforceAuthError, SalesforceConfigError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return FollowUpAnalysisSummaryResponse.model_validate(summary)
