"""Tests for branded Softude notification email templates."""

from __future__ import annotations

from integrations.email_templates import (
    build_artwork_mismatch_email,
    build_client_ack_email,
    build_email_overdue_notify,
    build_email_unanswered_digest,
    build_followup_owner_email,
    build_intake_owner_email,
    build_vendor_owner_email,
)


def test_intake_owner_email_is_branded_html() -> None:
    subject, text, html = build_intake_owner_email(
        category="quote_request",
        submitted_by="rahul@client.com",
        request_text="Need acrylic signage quote for lobby.",
        external_submission_id="EXT-1",
        submission_id="sub-123",
        monday={"board": {"url": "https://monday.com/boards/1"}},
    )

    assert "Quote Request" in subject
    assert "rahul@client.com" in text
    assert "Softude Ops Console" in html
    assert "Softude AI" in html
    assert "logo.png" in html
    assert "@keyframes softudeFadeUp" in html
    assert "softude-cta" in html
    assert "Quote Request" in html
    assert "Open in Monday" in html
    assert "https://monday.com/boards/1" in html
    assert "max-width:600px" in html


def test_vendor_owner_email_branded() -> None:
    subject, text, html = build_vendor_owner_email(
        status="ESCALATE",
        vendor_name="Acme Signs",
        project_id="P-101",
        hours_pending=72,
    )
    assert "Vendor Escalation" in subject
    assert "Acme Signs" in text
    assert "Vendor Agent" in html
    assert "Review in Ops Console" in html


def test_artwork_mismatch_email_branded() -> None:
    subject, text, html = build_artwork_mismatch_email(
        project_id="ART-9",
        artwork_width=48,
        artwork_height=36,
        spec_width=48,
        spec_height=32,
    )
    assert "Artwork review needed" in subject
    assert "48 × 36" in html
    assert "Artwork Agent" in html


def test_email_overdue_and_digest_branded() -> None:
    _, _, html = build_email_overdue_notify(thread_id="t-1", hours_pending=5)
    assert "Email Agent" in html
    assert "Unanswered" in html

    _, _, digest = build_email_unanswered_digest(
        threads=[{"thread_id": "t-1", "hours_pending": 5, "last_message_text": "Hello"}]
    )
    assert "Unanswered threads digest" in digest


def test_client_ack_email_branded() -> None:
    text, html = build_client_ack_email(body_text="Thanks for your quote request.")
    assert "Thanks for your quote request." in text
    assert "We received your message" in html
    assert "Client Services" in html


def test_followup_owner_email_keeps_escalation_accent(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_URL", "https://console.example.com/audit-log")
    subject, text, html = build_followup_owner_email(
        status="ESCALATE",
        project_id="P-203",
        project_name="Delta Infra",
        stage="Approved",
        days_inactive="12.2",
        dashboard_url_override="https://console.example.com/audit-log",
    )

    assert "Delta Infra" in subject
    assert "Delta Infra" in text
    assert "Project Escalation" in html
    assert "#ef4444" in html
    assert "Review in Ops Console" in html
    assert "https://console.example.com/audit-log" in html
