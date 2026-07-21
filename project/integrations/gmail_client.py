"""Gmail API client for fetching inbox threads and optional send.

Fetch auth uses ``gmail.readonly`` so existing ``GOOGLE_TOKEN_JSON`` /
``token.json`` keep working. Live post-approval mail needs a separate
re-consent with ``gmail.send`` (see ``SEND_SCOPES``) before
``WRITE_BACK_MODE=live`` can send.
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from integrations.email_text_cleaner import clean_email_text
from models.task import EmailMessage, EmailThread

# Must match scopes already granted on deployed GOOGLE_TOKEN_JSON.
SCOPES: list[str] = ["https://www.googleapis.com/auth/gmail.readonly"]

# Optional: Google account name + profile photo for the dashboard header.
# Re-consent once (delete token.json / refresh GOOGLE_TOKEN_JSON) so the token
# includes these; until then the UI falls back to initials from the Gmail address.
PROFILE_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# Required only for live owner/vendor notify emails — re-consent locally, then
# upload the new token.json as GOOGLE_TOKEN_JSON (and keep SEND in the token).
SEND_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = _PROJECT_ROOT / ".env"
CREDENTIALS_PATH = _PROJECT_ROOT / "credentials.json"
TOKEN_PATH = _PROJECT_ROOT / "token.json"

load_dotenv(ENV_PATH)


class GmailFetchError(Exception):
    """Raised when Gmail authentication or fetch fails."""


@dataclass(frozen=True)
class _ThreadFilterContext:
    """Metadata collected during fetch for optional post-build thread filtering."""

    last_sender_email: str
    subject: str
    searchable_text: str


def _oauth_client_config() -> dict[str, Any]:
    """Build Google Desktop OAuth client config from ``.env`` or ``credentials.json``.

    Preference order:
    1. ``GOOGLE_CLIENT_ID`` + ``GOOGLE_CLIENT_SECRET`` in the environment / ``.env``
    2. Fallback: ``credentials.json`` in the project root
    """
    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
    project_id = (os.getenv("GOOGLE_PROJECT_ID") or "").strip()

    if client_id and client_secret:
        installed: dict[str, Any] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
        if project_id:
            installed["project_id"] = project_id
        return {"installed": installed}

    if CREDENTIALS_PATH.exists():
        with CREDENTIALS_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)

    raise GmailFetchError(
        "Missing Gmail OAuth credentials. Set GOOGLE_CLIENT_ID and "
        "GOOGLE_CLIENT_SECRET in project/.env (see .env.example), "
        f"or place credentials.json at {CREDENTIALS_PATH}."
    )


def _active_oauth_scopes() -> list[str]:
    """Scopes used for browser consent / credential load.

    Set ``GMAIL_OAUTH_SCOPES=profile`` (or ``send``) to request profile photo
    (and/or send) on the next local re-consent. Default stays ``readonly`` so
    existing deployed tokens keep working.
    """
    mode = (os.getenv("GMAIL_OAUTH_SCOPES") or "readonly").strip().lower()
    if mode in {"profile", "userinfo", "full"}:
        return list(PROFILE_SCOPES)
    if mode in {"send", "send+profile", "all"}:
        return list(SEND_SCOPES)
    return list(SCOPES)


def _load_user_credentials() -> Credentials | None:
    """Load saved user OAuth token from env or ``token.json``."""
    scopes = _active_oauth_scopes()
    token_json = (os.getenv("GOOGLE_TOKEN_JSON") or "").strip()
    if token_json:
        return Credentials.from_authorized_user_info(json.loads(token_json), scopes)
    if TOKEN_PATH.exists():
        return Credentials.from_authorized_user_file(str(TOKEN_PATH), scopes)
    return None


def get_user_credentials() -> Credentials:
    """Return valid user OAuth credentials (refresh or local consent as needed)."""
    client_config = _oauth_client_config()
    cloud_host = bool(os.getenv("VERCEL") or os.getenv("DISABLE_GMAIL_BROWSER_OAUTH"))
    scopes = _active_oauth_scopes()

    try:
        creds = _load_user_credentials()

        if creds is None or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif cloud_host:
                raise GmailFetchError(
                    "Missing valid Gmail token for cloud deploy. "
                    "Set GOOGLE_TOKEN_JSON to your local token.json contents."
                )
            else:
                flow = InstalledAppFlow.from_client_config(client_config, scopes)
                creds = flow.run_local_server(port=0)

            if not cloud_host:
                TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

        return creds
    except GmailFetchError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface as a clear Gmail error
        raise GmailFetchError(
            f"Gmail authentication failed: {exc}. "
            "Check GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_TOKEN_JSON "
            "(or local credentials.json / token.json)."
        ) from exc


def get_gmail_service() -> Resource:
    """Build an authenticated Gmail API service (read-only).

    Loads/refreshes a stored token when possible. Locally, falls back to the
    browser OAuth flow. On cloud hosts, set ``GOOGLE_TOKEN_JSON`` (contents of
    ``token.json``) — interactive browser login is not available there.
    """
    return build("gmail", "v1", credentials=get_user_credentials())


def get_account_profile() -> dict[str, Any]:
    """Return the connected Gmail account email, name, and profile photo URL.

    Uses Gmail ``users.getProfile`` for the address (always available with
    ``gmail.readonly``). Tries Google OAuth userinfo for ``name`` / ``picture``
    when the token includes profile scopes; otherwise ``picture`` is null and
    the UI shows initials.
    """
    creds = get_user_credentials()
    service = build("gmail", "v1", credentials=creds)
    gmail_profile = service.users().getProfile(userId="me").execute()
    email = str(gmail_profile.get("emailAddress") or "").strip()

    result: dict[str, Any] = {
        "email": email,
        "name": email.split("@")[0].replace(".", " ").title() if email else "",
        "picture": None,
        "picture_source": "none",
    }

    if not creds.token:
        return result

    try:
        import urllib.request

        req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict):
            if payload.get("name"):
                result["name"] = str(payload["name"]).strip()
            if payload.get("email") and not email:
                result["email"] = str(payload["email"]).strip()
            picture = (payload.get("picture") or "").strip()
            if picture:
                result["picture"] = picture
                result["picture_source"] = "google"
    except Exception:  # noqa: BLE001 — profile photo is best-effort
        pass

    return result


def fetch_recent_threads(
    service: Any,
    max_results: int = 10,
    sender_filter: str | None = None,
    keyword_filter: str | None = None,
) -> list[EmailThread]:
    """Fetch recent inbox threads and convert them to EmailThread objects.

    Args:
        service: Authenticated Gmail API service from ``get_gmail_service()``.
        max_results: Maximum number of threads to return.
        sender_filter: Optional case-insensitive substring match against the
            last message's sender email address.
        keyword_filter: Optional case-insensitive substring match against the
            thread subject or any message body text.
    """
    try:
        profile = service.users().getProfile(userId="me").execute()
        own_email = str(profile.get("emailAddress", "")).lower()

        listed = (
            service.users()
            .threads()
            .list(userId="me", maxResults=max_results)
            .execute()
        )
        thread_refs = listed.get("threads", [])
        threads: list[EmailThread] = []
        filter_contexts: list[_ThreadFilterContext] = []

        for ref in thread_refs:
            thread_id = str(ref["id"])
            detail = (
                service.users()
                .threads()
                .get(userId="me", id=thread_id, format="full")
                .execute()
            )
            raw_messages = detail.get("messages", [])
            messages = [
                _gmail_message_to_email_message(raw, own_email, detail)
                for raw in raw_messages
            ]
            messages.sort(key=lambda message: message.timestamp)
            subject = ""
            for raw in raw_messages:
                headers = _headers_from_raw(raw)
                if headers.get("subject"):
                    subject = headers["subject"]
                    break
            threads.append(
                EmailThread(thread_id=thread_id, messages=messages, subject=subject)
            )
            filter_contexts.append(
                _build_thread_filter_context(raw_messages, messages)
            )

        return _apply_thread_filters(
            threads,
            filter_contexts,
            sender_filter=sender_filter,
            keyword_filter=keyword_filter,
        )
    except GmailFetchError:
        raise
    except HttpError as exc:
        raise GmailFetchError(
            f"Gmail API request failed: {exc}. "
            "Falling back to mock data is not automatic — check .env / credentials.json."
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise GmailFetchError(
            f"Gmail integration failed: {exc}. "
            "Falling back to mock data is not automatic — check .env / credentials.json."
        ) from exc


def _headers_from_raw(raw: dict[str, Any]) -> dict[str, str]:
    """Return lower-cased Gmail message headers."""
    return {
        header.get("name", "").lower(): header.get("value", "")
        for header in raw.get("payload", {}).get("headers", [])
    }


def _sender_email_from_header(from_header: str) -> str:
    """Extract a lowercased email address from a From header value."""
    _, address = parseaddr(from_header)
    return (address or from_header).strip().lower()


def _build_thread_filter_context(
    raw_messages: list[dict[str, Any]],
    messages: list[EmailMessage],
) -> _ThreadFilterContext:
    """Collect subject/sender metadata for optional post-build filtering."""
    subject = ""
    for raw in raw_messages:
        headers = _headers_from_raw(raw)
        if headers.get("subject"):
            subject = headers["subject"]
            break

    last_sender_email = ""
    if raw_messages:
        sorted_raw = sorted(
            raw_messages,
            key=lambda raw: int(raw.get("internalDate", "0")),
        )
        last_sender_email = _sender_email_from_header(
            _headers_from_raw(sorted_raw[-1]).get("from", "")
        )

    searchable_parts = [subject] if subject else []
    searchable_parts.extend(message.text for message in messages if message.text)
    searchable_text = "\n".join(searchable_parts)

    return _ThreadFilterContext(
        last_sender_email=last_sender_email,
        subject=subject,
        searchable_text=searchable_text,
    )


def _apply_thread_filters(
    threads: list[EmailThread],
    filter_contexts: list[_ThreadFilterContext],
    *,
    sender_filter: str | None,
    keyword_filter: str | None,
) -> list[EmailThread]:
    """Filter built threads by optional sender/keyword criteria (AND logic)."""
    sender_needle = (sender_filter or "").strip().lower()
    keyword_needle = (keyword_filter or "").strip().lower()
    if not sender_needle and not keyword_needle:
        return threads

    filtered: list[EmailThread] = []
    for thread, context in zip(threads, filter_contexts, strict=True):
        if sender_needle and sender_needle not in context.last_sender_email:
            continue
        if keyword_needle:
            if keyword_needle not in context.searchable_text.lower():
                continue
        filtered.append(thread)
    return filtered


def classify_sender(sender_email: str, own_email: str) -> str:
    """Classify a message sender as ``team``, ``internal``, or ``client``.

    - ``team``: exact match to the authenticated user's email
    - ``internal``: same email domain as the authenticated user (colleagues)
    - ``client``: any other external address

    Args:
        sender_email: Raw or parsed address from the From header
            (e.g. ``Name <user@domain.com>`` or ``user@domain.com``).
        own_email: Authenticated Gmail address (already lowercased preferred).
    """
    _, address = parseaddr(sender_email)
    address = (address or sender_email).strip().lower()
    own = (own_email or "").strip().lower()

    if not address:
        return "client"
    if own and address == own:
        return "team"
    if own and "@" in own:
        domain = own.rsplit("@", 1)[1]
        if domain and address.endswith("@" + domain):
            return "internal"
    return "client"


def _gmail_message_to_email_message(
    raw: dict[str, Any],
    own_email: str,
    thread_detail: dict[str, Any],
) -> EmailMessage:
    """Convert one Gmail API message dict into an EmailMessage."""
    headers = {
        header.get("name", "").lower(): header.get("value", "")
        for header in raw.get("payload", {}).get("headers", [])
    }
    from_header = headers.get("from", "")
    sender = classify_sender(from_header, own_email)

    internal_ms = int(raw.get("internalDate", "0"))
    timestamp = datetime.fromtimestamp(internal_ms / 1000, tz=timezone.utc)

    text = _extract_plain_text(raw.get("payload", {}))
    if not text:
        text = str(raw.get("snippet") or thread_detail.get("snippet") or "")

    plain_text = html_to_plain_text(text).strip()
    return EmailMessage(
        sender=sender,
        timestamp=timestamp,
        text=clean_email_text(plain_text),
        sender_email=_sender_email_from_header(from_header),
    )


def html_to_plain_text(value: str) -> str:
    """Convert HTML (or HTML-ish) email bodies into readable plain text."""
    if not value or "<" not in value:
        return value

    from integrations.email_text_cleaner import normalize_email_body

    text = html.unescape(value)
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", text)
    # Prefer link text; drop tracking URLs that spam the body after strip.
    text = re.sub(
        r'(?is)<a\b[^>]*>(.*?)</a>',
        lambda m: m.group(1),
        text,
    )
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|li|h[1-6]|td|th)\s*>", "\n", text)
    text = re.sub(r"(?i)<(p|div|tr|li|h[1-6]|td|th)\b[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return normalize_email_body(text)


def _extract_plain_text(payload: dict[str, Any]) -> str:
    """Best-effort plain-text extraction from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")

    if mime_type == "text/plain" and data:
        return _decode_body(data)

    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return _decode_body(part["body"]["data"])
        nested = _extract_plain_text(part)
        if nested:
            return nested

    if mime_type == "text/html" and data:
        return html_to_plain_text(_decode_body(data))

    if data and mime_type.startswith("text/"):
        return html_to_plain_text(_decode_body(data))

    return ""


def _decode_body(data: str) -> str:
    """Decode Gmail's URL-safe base64 body data."""
    padded = data + "=" * (-len(data) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
    return decoded.decode("utf-8", errors="replace")


def send_email(
    service: Any,
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Send an email via Gmail API, optionally with a rich HTML alternative.

    Requires a token that includes ``gmail.send`` (see ``SEND_SCOPES``). The
    default fetch token is read-only — re-consent locally and update
    ``GOOGLE_TOKEN_JSON`` before using ``WRITE_BACK_MODE=live`` for mail.
    """
    if body_html:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(body_text, "plain", "utf-8"))
        message.attach(MIMEText(body_html, "html", "utf-8"))
    else:
        message = MIMEText(body_text, "plain", "utf-8")
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    body: dict[str, Any] = {"raw": raw}
    if thread_id:
        body["threadId"] = thread_id

    try:
        sent = (
            service.users()
            .messages()
            .send(userId="me", body=body)
            .execute()
        )
    except HttpError as exc:
        raise GmailFetchError(
            f"Gmail send failed: {exc}. "
            "Token may be gmail.readonly only — re-consent with SEND_SCOPES "
            "and update GOOGLE_TOKEN_JSON."
        ) from exc

    return {
        "id": sent.get("id"),
        "threadId": sent.get("threadId"),
        "labelIds": sent.get("labelIds"),
    }
