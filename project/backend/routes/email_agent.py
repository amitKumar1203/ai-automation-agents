"""REST routes for the Email Reply Monitoring Agent."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import AnalysisSummaryResponse, GmailProfileResponse
from backend.services.agent_runs import run_email_batch
from integrations.gmail_client import GmailFetchError, get_account_profile

router = APIRouter()


@router.get("/profile", response_model=GmailProfileResponse)
def gmail_account_profile() -> GmailProfileResponse:
    """Return connected Gmail email / name / Google profile photo (if scoped)."""
    try:
        return GmailProfileResponse.model_validate(get_account_profile())
    except GmailFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/run", response_model=AnalysisSummaryResponse)
def run_email_agent(
    source: str = Query(
        default="gmail",
        pattern="^(mock|gmail)$",
        description="Data source: gmail (default) or mock (tests/CI)",
    ),
    sender_filter: Optional[str] = Query(
        default=None,
        description="Optional sender email/domain substring filter (live Gmail only)",
    ),
    keyword_filter: Optional[str] = Query(
        default=None,
        description="Optional subject/body keyword filter (live Gmail only)",
    ),
) -> AnalysisSummaryResponse:
    """Run the email reply agent via the Supervisor on mock or live Gmail threads."""
    try:
        summary = run_email_batch(
            use_real_gmail=(source == "gmail"),
            sender_filter=sender_filter,
            keyword_filter=keyword_filter,
            notify_owner=(source == "gmail"),
        )
    except GmailFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AnalysisSummaryResponse.model_validate(summary)
