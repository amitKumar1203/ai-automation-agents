"""Shared agent batch runners used by UI routes, webhooks, and cron."""

from __future__ import annotations

from typing import Any, Optional

from agents.email_reply_agent import EXTERNAL_SENDER_TYPES, EmailReplyMonitoringAgent
from backend.data_source import (
    get_approved_projects,
    get_email_threads,
    get_install_match_requests,
    get_project_activities,
    get_storefront_projects,
    get_vendor_requests,
)
from backend.services.kpi_cache import save_kpi_snapshot
from integrations.gmail_client import GmailFetchError
from integrations.monday_client import MondayConfigError, MondayFetchError
from integrations.salesforce_client import (
    SalesforceAuthError,
    SalesforceConfigError,
    SalesforceFetchError,
)
from models.agent_result import AgentResult
from models.task import ArtworkSubmission
from supervisor.agent_registry import get_agent
from supervisor.approval_policy import requires_human_approval
from supervisor.audit_log import log_execution
from supervisor.supervisor import Supervisor

_supervisor = Supervisor()


def run_email_batch(
    *,
    use_real_gmail: bool = True,
    sender_filter: Optional[str] = None,
    keyword_filter: Optional[str] = None,
    notify_owner: bool = True,
) -> dict[str, Any]:
    """Run email agent batch and refresh email KPIs."""
    threads = get_email_threads(
        use_real_gmail=use_real_gmail,
        sender_filter=sender_filter,
        keyword_filter=keyword_filter,
    )
    task_ids = [thread.thread_id for thread in threads]
    batch = _supervisor.run_batch("email_reply_monitoring", threads, task_ids)

    unanswered: list[dict[str, Any]] = []
    ok_count = 0
    results: list[dict[str, Any]] = []

    for entry in batch["results"]:
        thread = next(t for t in threads if t.thread_id == entry["task_id"])
        result = entry["result"]
        if thread.messages:
            last = thread.messages[-1]
            hours = float(result.data.get("hours_pending", 0.0))
            status = (
                "UNANSWERED"
                if hours > EmailReplyMonitoringAgent.THRESHOLD_HOURS
                and last.sender in EXTERNAL_SENDER_TYPES
                else "OK"
            )
            client_email = ""
            if last.sender in EXTERNAL_SENDER_TYPES and last.sender_email:
                client_email = last.sender_email
            else:
                for msg in reversed(thread.messages):
                    if msg.sender in EXTERNAL_SENDER_TYPES and msg.sender_email:
                        client_email = msg.sender_email
                        break
            card = {
                "thread_id": thread.thread_id,
                "status": status,
                "last_sender": last.sender,
                "last_message_text": last.text,
                "last_message_timestamp": last.timestamp.isoformat(),
                "hours_pending": hours,
                "confidence": result.confidence,
                "requires_approval": entry["final_approval_needed"],
                "reasoning": result.reasoning,
                "client_email": client_email,
                "subject": thread.subject or "",
            }
        else:
            card = {
                "thread_id": thread.thread_id,
                "status": "OK",
                "last_sender": "",
                "last_message_text": "",
                "last_message_timestamp": "",
                "hours_pending": 0.0,
                "confidence": result.confidence,
                "requires_approval": entry["final_approval_needed"],
                "reasoning": result.reasoning,
                "client_email": "",
                "subject": thread.subject or "",
            }
        results.append(card)
        if card["status"] == "UNANSWERED":
            unanswered.append(card)
        else:
            ok_count += 1

    summary = {
        "total_threads": len(results),
        "unanswered_count": len(unanswered),
        "ok_count": ok_count,
        "results": results,
    }
    save_kpi_snapshot(
        "email",
        {
            "total_threads": summary["total_threads"],
            "unanswered_count": summary["unanswered_count"],
            "ok_count": summary["ok_count"],
        },
    )

    notify_outcome = None
    # Owner digest and client ack are HITL: only after audit approve
    # (see action_executor._execute_email_notify). Automated batch polls
    # must not send outbound email without approval.
    if notify_owner and unanswered:
        summary["owner_notify"] = {
            "execution_status": "DEFERRED",
            "execution_detail": (
                "Owner notify deferred to audit approve (HITL)"
            ),
            "unanswered_count": len(unanswered),
        }

    if unanswered:
        summary["client_ack"] = {
            "execution_status": "DEFERRED",
            "execution_detail": (
                "Client ack deferred to audit approve when "
                "CLIENT_AUTO_ACK_ENABLED=true (HITL)"
            ),
        }

    return summary


def run_vendor_batch(*, use_real_monday: bool = True) -> dict[str, Any]:
    """Run vendor agent batch and refresh vendor KPIs."""
    requests = get_vendor_requests(use_real_monday=use_real_monday)
    task_ids = [req.project_id for req in requests]
    batch = _supervisor.run_batch("vendor_followup", requests, task_ids)

    results: list[dict[str, Any]] = []
    for entry in batch["results"]:
        request = next(r for r in requests if r.project_id == entry["task_id"])
        result = entry["result"]
        status = str(result.data.get("status", "WAITING"))
        results.append(
            {
                "vendor_name": request.vendor_name,
                "project_id": request.project_id,
                "status": status,
                "hours_pending": float(result.data.get("hours_pending", 0.0)),
                "confidence": result.confidence,
                "requires_approval": entry["final_approval_needed"],
                "reasoning": result.reasoning,
            }
        )

    summary = {
        "total_requests": len(results),
        "waiting_count": sum(1 for c in results if c["status"] == "WAITING"),
        "reminder_count": sum(1 for c in results if c["status"] == "SEND_REMINDER"),
        "escalate_count": sum(1 for c in results if c["status"] == "ESCALATE"),
        "results": results,
    }
    save_kpi_snapshot(
        "vendor",
        {
            "total_requests": summary["total_requests"],
            "waiting_count": summary["waiting_count"],
            "reminder_count": summary["reminder_count"],
            "escalate_count": summary["escalate_count"],
        },
    )
    return summary


def run_po_batch(*, use_real_salesforce: bool = True) -> dict[str, Any]:
    """Run PO agent batch and refresh PO KPIs."""
    projects = get_approved_projects(use_real_salesforce=use_real_salesforce)
    task_ids = [project.project_id for project in projects]
    batch = _supervisor.run_batch("po_automation", projects, task_ids)

    results: list[dict[str, Any]] = []
    for entry in batch["results"]:
        project = next(p for p in projects if p.project_id == entry["task_id"])
        result = entry["result"]
        status = str(result.data.get("status", "ALREADY_EXISTS"))
        draft_raw = result.data.get("draft_po")
        draft_po = draft_raw if isinstance(draft_raw, dict) else None
        results.append(
            {
                "project_id": project.project_id,
                "client_name": project.client_name,
                "vendor_name": project.vendor_name,
                "status": status,
                "estimated_amount": project.estimated_amount,
                "confidence": result.confidence,
                "requires_approval": entry["final_approval_needed"],
                "reasoning": result.reasoning,
                "draft_po": draft_po,
            }
        )

    summary = {
        "total_projects": len(results),
        "already_exists_count": sum(
            1 for c in results if c["status"] == "ALREADY_EXISTS"
        ),
        "ready_for_release_count": sum(
            1 for c in results if c["status"] == "PO_READY_FOR_RELEASE"
        ),
        "results": results,
    }
    save_kpi_snapshot(
        "po",
        {
            "total_projects": summary["total_projects"],
            "already_exists_count": summary["already_exists_count"],
            "ready_for_release_count": summary["ready_for_release_count"],
        },
    )
    return summary


def run_artwork_numeric(
    *,
    project_id: str,
    artwork_width_inches: float,
    artwork_height_inches: float,
    spec_width_inches: float,
    spec_height_inches: float,
    submitted_by: str = "dashboard",
) -> dict[str, Any]:
    """Run rule-based dimension check on user-entered values and audit-log it."""
    agent_name = "artwork_verification"
    task_id = (project_id or "").strip() or "numeric-check"
    submission = ArtworkSubmission(
        project_id=task_id,
        artwork_width_inches=artwork_width_inches,
        artwork_height_inches=artwork_height_inches,
        spec_width_inches=spec_width_inches,
        spec_height_inches=spec_height_inches,
        submitted_by=submitted_by or "dashboard",
    )
    outcome = _supervisor.execute_task(agent_name, submission, task_id)
    result = outcome["result"]

    card = {
        "project_id": task_id,
        "status": str(result.data.get("status", "MISMATCH")),
        "confidence": result.confidence,
        "requires_approval": outcome["final_approval_needed"],
        "reasoning": result.reasoning,
        "artwork_width_inches": float(result.data.get("artwork_width_inches", 0.0)),
        "artwork_height_inches": float(result.data.get("artwork_height_inches", 0.0)),
        "spec_width_inches": float(result.data.get("spec_width_inches", 0.0)),
        "spec_height_inches": float(result.data.get("spec_height_inches", 0.0)),
        "width_diff": float(result.data.get("width_diff", 0.0)),
        "height_diff": float(result.data.get("height_diff", 0.0)),
        "entry_id": outcome["entry_id"],
        "final_approval_needed": outcome["final_approval_needed"],
    }
    save_kpi_snapshot(
        "artwork",
        {
            "last_check": "numeric",
            "last_status": card["status"],
            "last_project_id": task_id,
        },
    )
    return card


def run_artwork_vision(
    *,
    artwork_image_bytes: bytes,
    artwork_media_type: str,
    spec_description: str,
    spec_image_bytes: Optional[bytes] = None,
    spec_media_type: Optional[str] = None,
    project_id: str = "",
) -> dict[str, Any]:
    """Run vision-based artwork verification and persist an audit log entry.

    Uses the registered artwork agent’s ``execute_vision`` path (not the
    rule-based ``execute``), then applies Supervisor approval policy + audit
    logging the same way as ``Supervisor.execute_task``.

    Returns:
        AgentResult-shaped dict plus ``entry_id`` and ``final_approval_needed``.
    """
    agent_name = "artwork_verification"
    task_id = (project_id or "").strip() or "vision-upload"
    agent = get_agent(agent_name)
    result = agent.execute_vision(
        artwork_image_bytes=artwork_image_bytes,
        artwork_media_type=artwork_media_type,
        spec_description=spec_description,
        spec_image_bytes=spec_image_bytes,
        spec_media_type=spec_media_type,
        project_id=task_id,
    )
    final_approval_needed = requires_human_approval(agent_name, result)
    entry_id = log_execution(agent_name, task_id, result, final_approval_needed)

    return {
        "data": result.data,
        "confidence": result.confidence,
        "requires_approval": result.requires_approval,
        "reasoning": result.reasoning,
        "entry_id": entry_id,
        "final_approval_needed": final_approval_needed,
    }


def _run_vision_agent_result(
    agent_name: str,
    task_id: str,
    result: AgentResult,
) -> dict[str, Any]:
    """Apply approval policy and audit logging for on-demand vision agents."""
    final_approval_needed = requires_human_approval(agent_name, result)
    entry_id = log_execution(agent_name, task_id, result, final_approval_needed)
    return {
        "data": result.data,
        "confidence": result.confidence,
        "requires_approval": result.requires_approval,
        "reasoning": result.reasoning,
        "entry_id": entry_id,
        "final_approval_needed": final_approval_needed,
    }


def run_rendering_vision(
    *,
    site_image_bytes: bytes,
    site_media_type: str,
    design_brief: str,
    artwork_image_bytes: Optional[bytes] = None,
    artwork_media_type: Optional[str] = None,
    project_id: str = "",
) -> dict[str, Any]:
    """Run AI Rendering vision analysis and audit-log it."""
    agent_name = "ai_rendering"
    task_id = (project_id or "").strip() or "rendering-upload"
    agent = get_agent(agent_name)
    result = agent.execute_vision(
        site_image_bytes=site_image_bytes,
        site_media_type=site_media_type,
        design_brief=design_brief,
        artwork_image_bytes=artwork_image_bytes,
        artwork_media_type=artwork_media_type,
        project_id=task_id,
    )
    return _run_vision_agent_result(agent_name, task_id, result)


def run_mockup_vision(
    *,
    site_image_bytes: bytes,
    site_media_type: str,
    artwork_image_bytes: bytes,
    artwork_media_type: str,
    brief: str = "",
    project_id: str = "",
    client_email: str = "",
) -> dict[str, Any]:
    """Run AI Mock-up vision analysis and audit-log it."""
    agent_name = "ai_mockup"
    task_id = (project_id or "").strip() or "mockup-upload"
    agent = get_agent(agent_name)
    result = agent.execute_vision(
        site_image_bytes=site_image_bytes,
        site_media_type=site_media_type,
        artwork_image_bytes=artwork_image_bytes,
        artwork_media_type=artwork_media_type,
        brief=brief,
        project_id=task_id,
        client_email=client_email,
    )
    return _run_vision_agent_result(agent_name, task_id, result)


def run_photo_analysis_vision(
    *,
    survey_image_bytes: bytes,
    survey_media_type: str,
    context: str = "",
    project_id: str = "",
    monday_item_id: str = "",
) -> dict[str, Any]:
    """Run Photo Analysis vision and audit-log it."""
    agent_name = "photo_analysis"
    task_id = (project_id or "").strip() or "photo-analysis-upload"
    agent = get_agent(agent_name)
    result = agent.execute_vision(
        survey_image_bytes=survey_image_bytes,
        survey_media_type=survey_media_type,
        context=context,
        project_id=task_id,
        monday_item_id=monday_item_id,
    )
    return _run_vision_agent_result(agent_name, task_id, result)


def run_installation_qc_vision(
    *,
    install_image_bytes: bytes,
    install_media_type: str,
    reference_image_bytes: bytes,
    reference_media_type: str,
    spec_notes: str = "",
    project_id: str = "",
    monday_item_id: str = "",
) -> dict[str, Any]:
    """Run Installation QC vision comparison and audit-log it."""
    agent_name = "installation_qc"
    task_id = (project_id or "").strip() or "installation-qc-upload"
    agent = get_agent(agent_name)
    result = agent.execute_vision(
        install_image_bytes=install_image_bytes,
        install_media_type=install_media_type,
        reference_image_bytes=reference_image_bytes,
        reference_media_type=reference_media_type,
        spec_notes=spec_notes,
        project_id=task_id,
        monday_item_id=monday_item_id,
    )
    return _run_vision_agent_result(agent_name, task_id, result)


def run_followup_batch(*, use_real_salesforce: bool = True) -> dict[str, Any]:
    """Run Automated Follow-Up on live Salesforce approved projects."""
    projects = get_project_activities(use_real_salesforce=use_real_salesforce)
    task_ids = [p.project_id for p in projects]
    batch = _supervisor.run_batch("automated_followup", projects, task_ids)

    results: list[dict[str, Any]] = []
    for entry in batch["results"]:
        project = next(p for p in projects if p.project_id == entry["task_id"])
        result = entry["result"]
        status = str(result.data.get("status", "OK"))
        results.append(
            {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "stage": project.stage,
                "status": status,
                "days_inactive": float(result.data.get("days_inactive", 0.0)),
                "owner_email": project.owner_email,
                "confidence": result.confidence,
                "requires_approval": entry["final_approval_needed"],
                "reasoning": result.reasoning,
                "entry_id": entry.get("entry_id"),
            }
        )

    summary = {
        "total_projects": len(results),
        "ok_count": sum(1 for c in results if c["status"] == "OK"),
        "followup_count": sum(1 for c in results if c["status"] == "SEND_FOLLOWUP"),
        "escalate_count": sum(1 for c in results if c["status"] == "ESCALATE"),
        "results": results,
    }
    save_kpi_snapshot(
        "followup",
        {
            "total_projects": summary["total_projects"],
            "ok_count": summary["ok_count"],
            "followup_count": summary["followup_count"],
            "escalate_count": summary["escalate_count"],
        },
    )
    return summary


def run_storefront_batch() -> dict[str, Any]:
    """Run Storefront Search on the live Monday board."""
    projects = get_storefront_projects()
    task_ids = [p.project_id for p in projects]
    batch = _supervisor.run_batch("storefront_search", projects, task_ids)

    results: list[dict[str, Any]] = []
    for entry in batch["results"]:
        project = next(p for p in projects if p.project_id == entry["task_id"])
        result = entry["result"]
        status = str(result.data.get("status") or "NOT_FOUND")
        results.append(
            {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "store_address": project.store_address,
                "status": status,
                "image_url": str(result.data.get("image_url") or ""),
                "image_source": str(result.data.get("image_source") or ""),
                "place_name": str(result.data.get("place_name") or ""),
                "match_confidence": result.data.get("match_confidence"),
                "monday_item_id": project.monday_item_id,
                "confidence": result.confidence,
                "requires_approval": entry["final_approval_needed"],
                "reasoning": result.reasoning,
                "entry_id": entry.get("entry_id"),
            }
        )

    summary = {
        "total_projects": len(results),
        "found_count": sum(1 for c in results if c["status"] == "FOUND"),
        "low_confidence_count": sum(
            1 for c in results if c["status"] == "LOW_CONFIDENCE"
        ),
        "not_found_count": sum(1 for c in results if c["status"] == "NOT_FOUND"),
        "skipped_count": sum(
            1
            for c in results
            if c["status"] in {"ALREADY_ATTACHED", "MISSING_ADDRESS", "SEARCH_FAILED"}
        ),
        "results": results,
    }
    save_kpi_snapshot(
        "storefront_search",
        {
            "total_projects": summary["total_projects"],
            "found_count": summary["found_count"],
            "low_confidence_count": summary["low_confidence_count"],
            "not_found_count": summary["not_found_count"],
        },
    )
    return summary


def run_installer_batch() -> dict[str, Any]:
    """Run Installer Matching on live Monday boards."""
    requests = get_install_match_requests()
    task_ids = [req.project.project_id for req in requests]
    batch = _supervisor.run_batch("installer_matching", requests, task_ids)

    results: list[dict[str, Any]] = []
    for entry in batch["results"]:
        request = next(
            req for req in requests if req.project.project_id == entry["task_id"]
        )
        project = request.project
        result = entry["result"]
        status = str(result.data.get("status") or "NO_MATCH")
        results.append(
            {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "install_region": project.install_region,
                "install_date": project.install_date,
                "status": status,
                "recommended_installer": str(
                    result.data.get("recommended_installer") or ""
                ),
                "recommended_installer_email": str(
                    result.data.get("recommended_installer_email") or ""
                ),
                "recommended_installer_region": str(
                    result.data.get("recommended_installer_region") or ""
                ),
                "match_type": str(result.data.get("match_type") or ""),
                "available_capacity": result.data.get("available_capacity"),
                "match_confidence": result.data.get("match_confidence"),
                "monday_item_id": project.monday_item_id,
                "confidence": result.confidence,
                "requires_approval": entry["final_approval_needed"],
                "reasoning": result.reasoning,
                "entry_id": entry.get("entry_id"),
            }
        )

    summary = {
        "total_projects": len(results),
        "matched_count": sum(1 for c in results if c["status"] == "MATCHED"),
        "low_confidence_count": sum(
            1 for c in results if c["status"] == "LOW_CONFIDENCE"
        ),
        "no_match_count": sum(1 for c in results if c["status"] == "NO_MATCH"),
        "skipped_count": sum(
            1
            for c in results
            if c["status"] in {"ALREADY_ASSIGNED", "MISSING_REGION"}
        ),
        "results": results,
    }
    save_kpi_snapshot(
        "installer_matching",
        {
            "total_projects": summary["total_projects"],
            "matched_count": summary["matched_count"],
            "low_confidence_count": summary["low_confidence_count"],
            "no_match_count": summary["no_match_count"],
        },
    )
    return summary


def run_all_live_batches() -> dict[str, Any]:
    """Cron/webhook helper: run email, vendor, PO, follow-up (live) + artwork."""
    outcomes: dict[str, Any] = {}
    try:
        outcomes["email"] = run_email_batch(use_real_gmail=True)
    except GmailFetchError as exc:
        outcomes["email"] = {"error": str(exc)}
    try:
        outcomes["vendor"] = run_vendor_batch(use_real_monday=True)
    except (MondayFetchError, MondayConfigError) as exc:
        outcomes["vendor"] = {"error": str(exc)}
    try:
        outcomes["po"] = run_po_batch(use_real_salesforce=True)
    except (SalesforceFetchError, SalesforceAuthError, SalesforceConfigError) as exc:
        outcomes["po"] = {"error": str(exc)}
    try:
        outcomes["followup"] = run_followup_batch(use_real_salesforce=True)
    except (SalesforceFetchError, SalesforceAuthError, SalesforceConfigError) as exc:
        outcomes["followup"] = {"error": str(exc)}
    try:
        outcomes["artwork"] = {
            "skipped": True,
            "reason": "Artwork checks are on-demand (numeric form or vision upload).",
        }
    except Exception as exc:  # noqa: BLE001
        outcomes["artwork"] = {"error": str(exc)}
    return outcomes
