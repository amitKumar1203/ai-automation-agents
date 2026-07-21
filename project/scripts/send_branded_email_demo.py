#!/usr/bin/env python3
"""Send a branded Softude demo notification email for visual QA."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from integrations.email_templates import build_intake_owner_email
from integrations.gmail_client import GmailFetchError, get_gmail_service, send_email


def main() -> None:
    recipient = (os.getenv("NOTIFY_OWNER_EMAIL") or "").strip()
    if not recipient:
        raise SystemExit("Set NOTIFY_OWNER_EMAIL in project/.env")

    subject, body_text, body_html = build_intake_owner_email(
        category="quote_request",
        submitted_by="rahul@clientcompany.com",
        request_text="Need acrylic signage quote for lobby, size 4x2 ft.",
        external_submission_id="DEMO-001",
        submission_id="demo-submission",
        monday={"board": {"url": "https://monday.com/boards/demo"}},
    )

    preview_path = ROOT / "fixtures" / "branded_email_demo.html"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(body_html, encoding="utf-8")
    print(f"Preview saved: {preview_path}")

    try:
        result = send_email(
            get_gmail_service(),
            to=recipient,
            subject=f"[Demo] {subject}",
            body_text=body_text,
            body_html=body_html,
        )
    except GmailFetchError as exc:
        print(f"Send failed: {exc}")
        print(
            "\nGmail token needs gmail.send scope. Re-consent locally:\n"
            "  1. Delete project/token.json\n"
            "  2. cd project && python3 -c \"from integrations.gmail_client import get_gmail_service; get_gmail_service()\"\n"
            "  3. Re-run: python3 scripts/send_branded_email_demo.py\n"
            "\nOpen the HTML preview in your browser meanwhile."
        )
        raise SystemExit(1) from exc

    print(f"Demo email sent to {recipient}")
    print(f"Gmail message id: {result.get('id')}")


if __name__ == "__main__":
    main()
