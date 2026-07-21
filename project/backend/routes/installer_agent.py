"""REST routes for the Installer Matching agent."""

from fastapi import APIRouter, HTTPException

from backend.schemas import InstallerAnalysisSummaryResponse
from backend.services.agent_runs import run_installer_batch
from integrations.monday_client import MondayConfigError, MondayFetchError

router = APIRouter()


@router.get("/run", response_model=InstallerAnalysisSummaryResponse)
def run_installer_agent() -> InstallerAnalysisSummaryResponse:
    """Rank installers for live Monday install projects and log to audit."""
    try:
        summary = run_installer_batch()
    except (MondayFetchError, MondayConfigError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return InstallerAnalysisSummaryResponse.model_validate(summary)
