"""Post-approval side effects for Phase 1 agents.

Runs only after a human APPROVES an audit entry. Default mode is dry-run
(``WRITE_BACK_MODE=dry_run``); set ``live`` to call external APIs.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from integrations.email_templates import (
    build_artwork_mismatch_email,
    build_email_overdue_notify,
    build_followup_owner_email,
    build_installer_owner_email,
    build_phase3_owner_email,
    build_vendor_owner_email,
)
from supervisor.write_back import (
    get_followup_notify_email,
    get_notify_owner_email,
    get_write_back_mode,
    is_live_write_back,
)

# Injectible callables for tests.
SendEmailFn = Callable[..., dict[str, Any]]
UpdateMondayFn = Callable[..., dict[str, Any]]
CreateSfFn = Callable[..., dict[str, Any]]
UpdateSfFn = Callable[..., dict[str, Any]]


def execute_approved_action(
    entry: dict[str, Any],
    *,
    send_email: SendEmailFn | None = None,
    update_monday_column: UpdateMondayFn | None = None,
    create_salesforce_record: CreateSfFn | None = None,
    update_salesforce_record: UpdateSfFn | None = None,
    sync_monday_po: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dispatch write-back for an approved audit entry.

    Args:
        entry: Full audit entry dict (must include agent_name + result.data).
        send_email / update_monday_column / create_* / update_*: optional
            overrides (tests). Live defaults load integration clients lazily.

    Returns:
        Dict with ``execution_status`` (SKIPPED|DRY_RUN|SUCCESS|FAILED) and
        ``execution_detail`` (JSON-serialisable summary string or dict).
    """
    existing_status = entry.get("execution_status")
    if existing_status in {"SUCCESS", "DRY_RUN"}:
        return {
            "execution_status": existing_status,
            "execution_detail": entry.get("execution_detail")
            or "Already executed; skipped duplicate run",
        }

    agent_name = entry.get("agent_name") or ""
    data = (entry.get("result") or {}).get("data") or {}
    mode = get_write_back_mode()

    try:
        if agent_name == "vendor_followup":
            outcome = _execute_vendor(
                data,
                mode=mode,
                send_email=send_email,
                update_monday_column=update_monday_column,
            )
        elif agent_name == "po_automation":
            outcome = _execute_po(
                data,
                mode=mode,
                create_salesforce_record=create_salesforce_record,
                update_salesforce_record=update_salesforce_record,
                sync_monday_po=sync_monday_po,
            )
        elif agent_name == "email_reply_monitoring":
            outcome = _execute_email_notify(data, mode=mode, send_email=send_email)
        elif agent_name == "artwork_verification":
            outcome = _execute_artwork_notify(data, mode=mode, send_email=send_email)
        elif agent_name == "automated_followup":
            outcome = _execute_followup_notify(data, mode=mode, send_email=send_email)
        elif agent_name == "storefront_search":
            outcome = _execute_storefront_attach(data, mode=mode)
        elif agent_name == "installer_matching":
            outcome = _execute_installer_match(
                data,
                mode=mode,
                send_email=send_email,
            )
        elif agent_name == "ai_rendering":
            outcome = _execute_rendering_notify(data, mode=mode, send_email=send_email)
        elif agent_name == "ai_mockup":
            outcome = _execute_mockup_share(data, mode=mode, send_email=send_email)
        elif agent_name == "photo_analysis":
            outcome = _execute_photo_analysis(
                data,
                mode=mode,
                send_email=send_email,
                update_monday_column=update_monday_column,
            )
        elif agent_name == "installation_qc":
            outcome = _execute_installation_qc(
                data,
                mode=mode,
                send_email=send_email,
                update_monday_column=update_monday_column,
            )
        else:
            outcome = {
                "execution_status": "SKIPPED",
                "execution_detail": f"No post-approval action for agent '{agent_name}'",
            }
    except Exception as exc:  # noqa: BLE001 — persist failure on the audit row
        outcome = {
            "execution_status": "FAILED",
            "execution_detail": {"error": str(exc)},
        }

    status_value = str(data.get("status") or "")
    if status_value == "ESCALATE" and outcome.get("execution_status") in {
        "SUCCESS",
        "DRY_RUN",
    }:
        from supervisor.escalation import merge_escalation_marker

        outcome = {
            **outcome,
            "execution_detail": _detail(
                merge_escalation_marker(
                    outcome.get("execution_detail"),
                    reason="agent_escalate",
                    agent_name=agent_name,
                    task_id=entry.get("task_id"),
                    entry_id=entry.get("id"),
                    extra={"status": status_value},
                )
            ),
        }

    if outcome.get("execution_status") == "FAILED":
        try:
            from backend.services.agent_job_worker import enqueue_writeback_retry

            entry_id = str(entry.get("id") or "").strip()
            if entry_id:
                enqueue_writeback_retry(entry_id)
        except Exception:
            pass

    return outcome


def _detail(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


def _execute_vendor(
    data: dict[str, Any],
    *,
    mode: str,
    send_email: SendEmailFn | None,
    update_monday_column: UpdateMondayFn | None,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status not in {"SEND_REMINDER", "ESCALATE"}:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Vendor status '{status}' has no write-back",
        }

    vendor_name = str(data.get("vendor_name") or "vendor")
    project_id = str(data.get("project_id") or "")
    hours_pending = data.get("hours_pending")
    monday_item_id = data.get("monday_item_id")
    owner = get_notify_owner_email()

    planned: dict[str, Any] = {
        "action": status,
        "vendor_name": vendor_name,
        "project_id": project_id,
        "hours_pending": hours_pending,
        "monday_item_id": monday_item_id,
        "notify_owner": owner,
        "mode": mode,
    }

    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    results: dict[str, Any] = {"planned": planned, "effects": {}}

    if owner:
        subject, body_text, body_html = build_vendor_owner_email(
            status=status,
            vendor_name=vendor_name,
            project_id=project_id,
            hours_pending=hours_pending or "—",
        )
        email_fn = send_email or _default_send_email
        results["effects"]["email"] = email_fn(
            to=owner,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )

    if status == "ESCALATE" and monday_item_id:
        monday_fn = update_monday_column or _default_update_monday
        results["effects"]["monday"] = monday_fn(
            item_id=str(monday_item_id),
            column_title="Quote Received",
            label="Escalate",
        )
    elif status == "ESCALATE" and not monday_item_id:
        results["effects"]["monday"] = {
            "skipped": True,
            "reason": "monday_item_id missing from agent result",
        }

    return {"execution_status": "SUCCESS", "execution_detail": _detail(results)}


def _execute_po(
    data: dict[str, Any],
    *,
    mode: str,
    create_salesforce_record: CreateSfFn | None,
    update_salesforce_record: UpdateSfFn | None,
    sync_monday_po: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status != "PO_READY_FOR_RELEASE":
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"PO status '{status}' has no write-back",
        }

    draft = data.get("draft_po") or {}
    salesforce_id = data.get("salesforce_id")
    import os

    po_object = (os.getenv("SALESFORCE_PO_OBJECT") or "").strip()
    project_id = str(draft.get("project_id") or data.get("project_id") or "")
    po_number = f"PO-{project_id}" if project_id else "PO-UNKNOWN"

    planned: dict[str, Any] = {
        "action": "RELEASE_PO",
        "project_id": project_id,
        "po_number": po_number,
        "draft_po": draft,
        "salesforce_id": salesforce_id,
        "po_object": po_object or None,
        "monday_po_sync": True,
        "mode": mode,
    }

    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    results: dict[str, Any] = {"planned": planned, "effects": {}}
    create_fn = create_salesforce_record or _default_create_sf
    update_fn = update_salesforce_record or _default_update_sf

    if po_object:
        fields = {
            "Name": po_number,
            "Project_Id__c": project_id or None,
            "Client_Name__c": draft.get("client_name") or data.get("client_name"),
            "Vendor_Name__c": draft.get("vendor_name"),
            "Amount__c": draft.get("estimated_amount"),
        }
        fields = {k: v for k, v in fields.items() if v is not None}
        results["effects"]["po_create"] = create_fn(po_object, fields)
        created_id = (results["effects"]["po_create"] or {}).get("id")
        if created_id:
            po_number = str(created_id)
            results["effects"]["po_number"] = po_number

    if salesforce_id:
        results["effects"]["mark_po_exists"] = update_fn(
            "Approved_Project__c",
            str(salesforce_id),
            {"PO_Exists__c": True},
        )
    else:
        results["effects"]["mark_po_exists"] = {
            "skipped": True,
            "reason": "salesforce_id missing from agent result",
        }

    monday_fn = sync_monday_po or _default_sync_monday_po
    results["effects"]["monday_po_sync"] = monday_fn(
        project_id=project_id,
        po_number=po_number,
    )

    return {"execution_status": "SUCCESS", "execution_detail": _detail(results)}


def _execute_email_notify(
    data: dict[str, Any],
    *,
    mode: str,
    send_email: SendEmailFn | None,
) -> dict[str, Any]:
    from backend.services.client_ack import is_client_auto_ack_enabled, send_client_acks

    owner = get_notify_owner_email()
    thread_id = data.get("thread_id")
    hours_pending = data.get("hours_pending")
    status = str(data.get("status") or "UNANSWERED")
    planned: dict[str, Any] = {
        "action": "OWNER_NOTIFY",
        "status": status,
        "thread_id": thread_id,
        "hours_pending": hours_pending,
        "notify_owner": owner,
        "client_ack_enabled": is_client_auto_ack_enabled(),
        "mode": mode,
    }

    if status not in {"UNANSWERED", "CRITICAL"}:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Email status '{status}' has no write-back",
        }

    if not owner and not is_client_auto_ack_enabled():
        return {
            "execution_status": "SKIPPED",
            "execution_detail": (
                "NOTIFY_OWNER_EMAIL not configured and CLIENT_AUTO_ACK_ENABLED is off"
            ),
        }

    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    results: dict[str, Any] = {"planned": planned, "effects": {}}
    email_fn = send_email or _default_send_email

    if owner:
        subject, body_text, body_html = build_email_overdue_notify(
            thread_id=str(thread_id or "—"),
            hours_pending=hours_pending or "—",
            status=status,
            priority=str(data.get("priority") or "normal"),
            draft_reply=str(data.get("draft_reply") or ""),
        )
        results["effects"]["owner_email"] = email_fn(
            to=owner,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )

    if is_client_auto_ack_enabled():
        results["effects"]["client_ack"] = send_client_acks(
            [
                {
                    "thread_id": thread_id,
                    "client_email": data.get("client_email") or "",
                    "subject": data.get("subject") or "",
                    "hours_pending": hours_pending,
                }
            ],
            send_email=email_fn,
        )

    return {
        "execution_status": "SUCCESS",
        "execution_detail": _detail(results),
    }


def _execute_artwork_notify(
    data: dict[str, Any],
    *,
    mode: str,
    send_email: SendEmailFn | None,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status != "MISMATCH":
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Artwork status '{status}' has no write-back",
        }

    owner = get_notify_owner_email()
    planned = {
        "action": "ARTWORK_MISMATCH_NOTIFY",
        "project_id": data.get("project_id"),
        "status": status,
        "notify_owner": owner,
        "mode": mode,
    }

    if not owner:
        return {
            "execution_status": "DRY_RUN" if not is_live_write_back() else "SKIPPED",
            "execution_detail": _detail(
                {**planned, "note": "No NOTIFY_OWNER_EMAIL; logged only"}
            ),
        }

    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    email_fn = send_email or _default_send_email
    subject, body_text, body_html = build_artwork_mismatch_email(
        project_id=str(data.get("project_id") or "—"),
        status=status,
        artwork_width=data.get("artwork_width_inches"),
        artwork_height=data.get("artwork_height_inches"),
        spec_width=data.get("spec_width_inches"),
        spec_height=data.get("spec_height_inches"),
    )
    effect = email_fn(
        to=owner,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
    return {
        "execution_status": "SUCCESS",
        "execution_detail": _detail({"planned": planned, "effects": {"email": effect}}),
    }


def _execute_followup_notify(
    data: dict[str, Any],
    *,
    mode: str,
    send_email: SendEmailFn | None,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status not in {"SEND_FOLLOWUP", "ESCALATE"}:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Follow-up status '{status}' has no write-back",
        }

    # Prefer per-project owner, then FOLLOWUP_NOTIFY_EMAIL, then NOTIFY_OWNER_EMAIL.
    notify_to = (
        str(data.get("owner_email") or "").strip()
        or get_followup_notify_email()
    )
    planned = {
        "action": status,
        "project_id": data.get("project_id"),
        "project_name": data.get("project_name"),
        "days_inactive": data.get("days_inactive"),
        "notify_to": notify_to,
        "mode": mode,
    }

    if not notify_to:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": (
                "No notify target — set FOLLOWUP_NOTIFY_EMAIL or NOTIFY_OWNER_EMAIL "
                "in .env (or project owner_email on the record)"
            ),
        }

    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    email_fn = send_email or _default_send_email
    project_id = str(data.get("project_id") or "—")
    project_name = str(data.get("project_name") or "Unnamed project")
    stage = str(data.get("stage") or "Not specified")
    days_inactive = str(data.get("days_inactive") or "—")

    subject, body_text, body_html = build_followup_owner_email(
        status=status,
        project_id=project_id,
        project_name=project_name,
        stage=stage,
        days_inactive=days_inactive,
        dashboard_url_override=(
            os.getenv("DASHBOARD_URL")
            or "https://ai-automation-agents-plum.vercel.app/audit-log"
        ).strip(),
    )

    effect = email_fn(
        to=notify_to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
    return {
        "execution_status": "SUCCESS",
        "execution_detail": _detail({"planned": planned, "effects": {"email": effect}}),
    }


def _execute_storefront_attach(
    data: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status not in {"FOUND", "LOW_CONFIDENCE"}:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Storefront status '{status}' has no write-back",
        }

    item_id = str(data.get("monday_item_id") or "").strip()
    image_url = str(data.get("image_url") or "").strip()
    planned = {
        "action": "ATTACH_STOREFRONT_IMAGE",
        "project_id": data.get("project_id"),
        "project_name": data.get("project_name"),
        "store_address": data.get("store_address"),
        "monday_item_id": item_id,
        "image_url": image_url,
        "mode": mode,
    }
    if not item_id or not image_url:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": _detail(
                {**planned, "reason": "monday_item_id or image_url missing"}
            ),
        }
    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    from integrations.monday_storefront_client import update_storefront_image_column

    effect = update_storefront_image_column(item_id=item_id, image_url=image_url)
    return {
        "execution_status": "SUCCESS",
        "execution_detail": _detail({"planned": planned, "effects": {"monday": effect}}),
    }


def _execute_installer_match(
    data: dict[str, Any],
    *,
    mode: str,
    send_email: SendEmailFn | None,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status not in {"MATCHED", "LOW_CONFIDENCE"}:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Installer status '{status}' has no write-back",
        }

    item_id = str(data.get("monday_item_id") or "").strip()
    installer_name = str(data.get("recommended_installer") or "").strip()
    planned = {
        "action": "ASSIGN_INSTALLER",
        "project_id": data.get("project_id"),
        "project_name": data.get("project_name"),
        "install_region": data.get("install_region"),
        "monday_item_id": item_id,
        "recommended_installer": installer_name,
        "recommended_installer_email": data.get("recommended_installer_email"),
        "mode": mode,
    }
    if not item_id or not installer_name:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": _detail(
                {**planned, "reason": "monday_item_id or recommended_installer missing"}
            ),
        }
    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    from integrations.monday_installer_client import update_assigned_installer_column

    results: dict[str, Any] = {"planned": planned, "effects": {}}
    results["effects"]["monday"] = update_assigned_installer_column(
        item_id=item_id,
        installer_name=installer_name,
    )

    owner = get_notify_owner_email()
    if owner:
        subject, body_text, body_html = build_installer_owner_email(
            project_id=str(data.get("project_id") or ""),
            project_name=str(data.get("project_name") or ""),
            install_region=str(data.get("install_region") or ""),
            installer_name=installer_name,
            installer_email=str(data.get("recommended_installer_email") or ""),
            installer_region=str(data.get("recommended_installer_region") or ""),
            match_type=str(data.get("match_type") or ""),
        )
        email_fn = send_email or _default_send_email
        results["effects"]["email"] = email_fn(
            to=owner,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )

    return {"execution_status": "SUCCESS", "execution_detail": _detail(results)}


def _execute_rendering_notify(
    data: dict[str, Any],
    *,
    mode: str,
    send_email: SendEmailFn | None,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status != "READY_FOR_REVIEW":
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Rendering status '{status}' has no write-back",
        }
    owner = get_notify_owner_email()
    project_id = str(data.get("project_id") or "—")
    planned = {
        "action": "RENDERING_REVIEW_NOTIFY",
        "project_id": project_id,
        "status": status,
        "notify_owner": owner,
        "mode": mode,
    }
    if not owner:
        return {
            "execution_status": "DRY_RUN" if not is_live_write_back() else "SKIPPED",
            "execution_detail": _detail({**planned, "note": "No NOTIFY_OWNER_EMAIL"}),
        }
    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    email_fn = send_email or _default_send_email
    subject, body_text, body_html = build_phase3_owner_email(
        agent_label="AI Rendering",
        project_id=project_id,
        status=status,
        headline="Rendering ready for designer review",
        summary=str(data.get("design_alternatives") or data.get("notes") or ""),
        rows=[
            ("Window type", str(data.get("window_type") or "—")),
            ("Color palette", str(data.get("color_palette") or "—")),
        ],
    )
    effect = email_fn(
        to=owner, subject=subject, body_text=body_text, body_html=body_html
    )
    return {
        "execution_status": "SUCCESS",
        "execution_detail": _detail({"planned": planned, "effects": {"email": effect}}),
    }


def _execute_mockup_share(
    data: dict[str, Any],
    *,
    mode: str,
    send_email: SendEmailFn | None,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status != "READY_FOR_EXTERNAL_SHARE":
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Mock-up status '{status}' has no write-back",
        }
    owner = get_notify_owner_email()
    project_id = str(data.get("project_id") or "—")
    client_email = str(data.get("client_email") or "").strip()
    planned = {
        "action": "MOCKUP_EXTERNAL_SHARE_GATE",
        "project_id": project_id,
        "client_email": client_email or None,
        "notify_owner": owner,
        "mode": mode,
    }
    if not owner:
        return {
            "execution_status": "DRY_RUN" if not is_live_write_back() else "SKIPPED",
            "execution_detail": _detail({**planned, "note": "No NOTIFY_OWNER_EMAIL"}),
        }
    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    email_fn = send_email or _default_send_email
    subject, body_text, body_html = build_phase3_owner_email(
        agent_label="AI Mock-up",
        project_id=project_id,
        status=status,
        headline="Mock-up approved for external share",
        summary=str(data.get("alignment_notes") or ""),
        rows=[
            ("Scale", str(data.get("scale_assessment") or "—")),
            ("Client email", client_email or "(not provided)"),
        ],
    )
    effect = email_fn(
        to=owner, subject=subject, body_text=body_text, body_html=body_html
    )
    return {
        "execution_status": "SUCCESS",
        "execution_detail": _detail({"planned": planned, "effects": {"email": effect}}),
    }


def _execute_photo_analysis(
    data: dict[str, Any],
    *,
    mode: str,
    send_email: SendEmailFn | None,
    update_monday_column: UpdateMondayFn | None,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status != "ISSUES_FOUND":
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Photo analysis status '{status}' has no write-back",
        }
    owner = get_notify_owner_email()
    item_id = str(data.get("monday_item_id") or "").strip()
    project_id = str(data.get("project_id") or "—")
    notes_text = "\n".join(
        filter(
            None,
            [
                str(data.get("branding_detected") or ""),
                str(data.get("installation_type") or ""),
                str(data.get("issues") or ""),
            ],
        )
    )
    planned = {
        "action": "PHOTO_ANALYSIS_ISSUES",
        "project_id": project_id,
        "monday_item_id": item_id or None,
        "notify_owner": owner,
        "mode": mode,
    }
    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    results: dict[str, Any] = {"planned": planned, "effects": {}}
    if item_id and notes_text:
        from integrations.monday_client import update_text_column_by_title

        try:
            results["effects"]["monday"] = update_text_column_by_title(
                item_id=item_id,
                column_title="Survey Notes",
                text=notes_text[:5000],
            )
        except Exception as exc:  # noqa: BLE001
            results["effects"]["monday"] = {"error": str(exc)}

    if owner:
        email_fn = send_email or _default_send_email
        subject, body_text, body_html = build_phase3_owner_email(
            agent_label="Photo Analysis",
            project_id=project_id,
            status=status,
            headline="Survey photo issues detected",
            summary=str(data.get("issues") or ""),
            rows=[
                ("Branding", str(data.get("branding_detected") or "—")),
                ("Installation type", str(data.get("installation_type") or "—")),
            ],
        )
        results["effects"]["email"] = email_fn(
            to=owner, subject=subject, body_text=body_text, body_html=body_html
        )

    return {"execution_status": "SUCCESS", "execution_detail": _detail(results)}


def _execute_installation_qc(
    data: dict[str, Any],
    *,
    mode: str,
    send_email: SendEmailFn | None,
    update_monday_column: UpdateMondayFn | None,
) -> dict[str, Any]:
    status = str(data.get("status") or "")
    if status not in {"FAIL", "NEEDS_REVIEW"}:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": f"Installation QC status '{status}' has no write-back",
        }
    owner = get_notify_owner_email()
    item_id = str(data.get("monday_item_id") or "").strip()
    project_id = str(data.get("project_id") or "—")
    monday_label = "Fail" if status == "FAIL" else "Needs Review"
    planned = {
        "action": "INSTALLATION_QC",
        "project_id": project_id,
        "status": status,
        "monday_item_id": item_id or None,
        "notify_owner": owner,
        "mode": mode,
    }
    if not is_live_write_back():
        return {"execution_status": "DRY_RUN", "execution_detail": _detail(planned)}

    results: dict[str, Any] = {"planned": planned, "effects": {}}
    if item_id:
        monday_fn = update_monday_column or _default_update_monday
        try:
            results["effects"]["monday"] = monday_fn(
                item_id=item_id,
                column_title="QC Status",
                label=monday_label,
            )
        except Exception as exc:  # noqa: BLE001
            results["effects"]["monday"] = {"error": str(exc)}

    if owner:
        email_fn = send_email or _default_send_email
        subject, body_text, body_html = build_phase3_owner_email(
            agent_label="Installation QC",
            project_id=project_id,
            status=status,
            headline=f"Installation QC: {status.replace('_', ' ').title()}",
            summary=str(data.get("defects") or data.get("recommendation") or ""),
            rows=[
                ("Alignment", str(data.get("alignment_score") or "—")),
                ("Recommendation", str(data.get("recommendation") or "—")),
            ],
        )
        results["effects"]["email"] = email_fn(
            to=owner, subject=subject, body_text=body_text, body_html=body_html
        )

    return {"execution_status": "SUCCESS", "execution_detail": _detail(results)}


def _default_send_email(*, to: str, subject: str, body_text: str, **kwargs: Any) -> dict:
    from integrations.gmail_client import get_gmail_service, send_email as gmail_send

    return gmail_send(
        get_gmail_service(),
        to=to,
        subject=subject,
        body_text=body_text,
        **kwargs,
    )


def _default_update_monday(
    *,
    item_id: str,
    column_title: str,
    label: str,
) -> dict:
    from integrations.monday_client import update_status_column_by_title

    return update_status_column_by_title(
        item_id=item_id,
        column_title=column_title,
        label=label,
    )


def _default_create_sf(object_api_name: str, fields: dict[str, Any]) -> dict:
    from integrations.salesforce_client import create_record

    return create_record(object_api_name, fields)


def _default_update_sf(
    object_api_name: str,
    record_id: str,
    fields: dict[str, Any],
) -> dict:
    from integrations.salesforce_client import update_record

    return update_record(object_api_name, record_id, fields)


def _default_sync_monday_po(*, project_id: str, po_number: str) -> dict:
    from integrations.monday_client import sync_po_number_to_monday

    return sync_po_number_to_monday(project_id=project_id, po_number=po_number)
