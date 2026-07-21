"""Data source selection for agent inputs (mock vs live integrations)."""

from datetime import datetime, timezone
from typing import Optional

from models.task import EmailThread, InstallMatchRequest, InstallProject, InstallerProfile, ProjectActivity, ProjectApproval, StorefrontProject, VendorQuoteRequest


def get_email_threads(
    use_real_gmail: bool = False,
    sender_filter: Optional[str] = None,
    keyword_filter: Optional[str] = None,
) -> list[EmailThread]:
    """Return email threads from mock data or live Gmail.

    Args:
        use_real_gmail: When True, fetch real inbox threads via Gmail API.
            When False, return sample mock threads.
        sender_filter: Optional sender email/domain substring filter (live Gmail only).
        keyword_filter: Optional subject/body keyword filter (live Gmail only).

    Raises:
        GmailFetchError: If live Gmail fetch/auth fails (propagated for API 502).
    """
    if not use_real_gmail:
        from backend.mock_data import get_sample_threads

        return get_sample_threads(reference_time=datetime.now(timezone.utc))

    from integrations.gmail_client import (
        GmailFetchError,
        fetch_recent_threads,
        get_gmail_service,
    )

    try:
        service = get_gmail_service()
        return fetch_recent_threads(
            service,
            sender_filter=sender_filter,
            keyword_filter=keyword_filter,
        )
    except GmailFetchError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise GmailFetchError(
            f"Gmail integration failed: {exc}. "
            "Falling back to mock data is not automatic — "
            "check project/.env (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET) or token.json."
        ) from exc


def get_vendor_requests(use_real_monday: bool = False) -> list[VendorQuoteRequest]:
    """Return vendor quote requests from mock data or live Monday.com.

    Args:
        use_real_monday: When True, fetch items from the configured Monday.com
            board. When False, return sample mock requests.

    Raises:
        MondayFetchError: If live Monday.com fetch/auth fails (propagated for API 502).
        MondayConfigError: If Monday.com credentials are missing (propagated for API 502).
    """
    if not use_real_monday:
        from backend.mock_data import get_sample_vendor_requests

        return get_sample_vendor_requests(reference_time=datetime.now(timezone.utc))

    from integrations.monday_client import (
        MondayConfigError,
        MondayFetchError,
        fetch_vendor_requests,
    )

    try:
        return fetch_vendor_requests()
    except (MondayFetchError, MondayConfigError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise MondayFetchError(
            f"Monday.com integration failed: {exc}. "
            "Falling back to mock data is not automatic — "
            "check project/.env (MONDAY_API_TOKEN / MONDAY_BOARD_ID)."
        ) from exc


def get_approved_projects(
    use_real_salesforce: bool = False,
) -> list[ProjectApproval]:
    """Return approved projects from mock data or live Salesforce.

    Args:
        use_real_salesforce: When True, query ``Approved_Project__c`` via Salesforce.
            When False, return sample mock projects.

    Raises:
        SalesforceConfigError: If Salesforce credentials are missing.
        SalesforceAuthError: If OAuth login fails.
        SalesforceFetchError: If the SOQL query or mapping fails.
    """
    if not use_real_salesforce:
        from backend.mock_data import get_sample_project_approvals

        return get_sample_project_approvals(reference_time=datetime.now(timezone.utc))

    from integrations.salesforce_client import (
        SalesforceAuthError,
        SalesforceConfigError,
        SalesforceFetchError,
        fetch_approved_projects,
        get_salesforce_access_token,
    )

    try:
        access_token, instance_url = get_salesforce_access_token()
        return fetch_approved_projects(
            access_token=access_token,
            instance_url=instance_url,
        )
    except (SalesforceFetchError, SalesforceAuthError, SalesforceConfigError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise SalesforceFetchError(
            f"Salesforce integration failed: {exc}. "
            "Falling back to mock data is not automatic — "
            "check project/.env (SALESFORCE_CLIENT_ID / SECRET / USERNAME / "
            "PASSWORD / DOMAIN)."
        ) from exc


def get_project_activities(*, use_real_salesforce: bool = True) -> list[ProjectActivity]:
    """Return live project activity rows for Automated Follow-Up.

    Uses Salesforce ``Approved_Project__c`` (same org as the PO agent).
    ``Approved_Date__c`` is treated as last activity for stall detection.
    Mock data is not used.
    """
    from integrations.salesforce_client import (
        SalesforceAuthError,
        SalesforceConfigError,
        SalesforceFetchError,
    )

    if not use_real_salesforce:
        raise SalesforceFetchError(
            "Automated Follow-Up requires live Salesforce data "
            "(source=salesforce). Mock data is disabled."
        )

    try:
        projects = get_approved_projects(use_real_salesforce=True)
    except (SalesforceFetchError, SalesforceAuthError, SalesforceConfigError):
        raise

    # Prefer Admin DB / FOLLOWUP_NOTIFY_EMAIL, then default owner.
    from supervisor.write_back import get_followup_notify_email

    notify = (get_followup_notify_email() or "").strip()

    activities: list[ProjectActivity] = []
    for project in projects:
        activities.append(
            ProjectActivity(
                project_id=project.project_id,
                project_name=project.client_name or project.project_id,
                last_activity_at=project.approved_at,
                stage="Approved",
                owner_email=notify,
                monday_item_id=None,
            )
        )
    return activities


def get_storefront_projects() -> list[StorefrontProject]:
    """Return storefront projects from the live Monday.com board."""
    from integrations.monday_storefront_client import fetch_storefront_projects

    return fetch_storefront_projects()


def get_install_match_requests() -> list[InstallMatchRequest]:
    """Return install projects with installer roster from live Monday boards."""
    from integrations.monday_installer_client import (
        fetch_install_projects,
        fetch_installer_roster,
    )

    roster = fetch_installer_roster()
    return [
        InstallMatchRequest(project=project, installers=roster)
        for project in fetch_install_projects()
    ]
