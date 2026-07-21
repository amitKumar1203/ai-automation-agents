"""Salesforce API client for approved projects and optional PO write-back.

Auth preference order:
1. Stored refresh token (``salesforce_token.json`` / ``SALESFORCE_REFRESH_TOKEN``)
2. OAuth 2.0 Username-Password flow (if username/password configured)
3. One-time local browser Authorization Code flow (saves a refresh token)

Create/update helpers are used only when post-approval write-back is enabled
(``WRITE_BACK_MODE=live``).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

import requests
from dotenv import load_dotenv

from models.task import ProjectApproval

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = _PROJECT_ROOT / ".env"
TOKEN_PATH = _PROJECT_ROOT / "salesforce_token.json"
PKCE_STATE_PATH = _PROJECT_ROOT / ".salesforce_pkce.json"
REQUEST_TIMEOUT_SECONDS = 10
API_VERSION = "v59.0"
LOCAL_CALLBACK_HOST = "localhost"
LOCAL_CALLBACK_PORT = 8765
_DEFAULT_REDIRECT_URI = f"http://{LOCAL_CALLBACK_HOST}:{LOCAL_CALLBACK_PORT}/callback"


def get_redirect_uri() -> str:
    """Return the OAuth callback URL (must match Connected App exactly)."""
    return (os.getenv("SALESFORCE_REDIRECT_URI") or _DEFAULT_REDIRECT_URI).strip()

_REQUIRED_ENV_KEYS = (
    "SALESFORCE_CLIENT_ID",
    "SALESFORCE_CLIENT_SECRET",
    "SALESFORCE_DOMAIN",
)

_SOQL_QUERY = (
    "SELECT Id, Name, Client_Name__c, Vendor_Name__c, Approved_Date__c, "
    "PO_Exists__c, Estimated_Amount__c FROM Approved_Project__c"
)

load_dotenv(ENV_PATH, override=True)


class SalesforceConfigError(Exception):
    """Raised when Salesforce credentials or domain are missing."""


class SalesforceAuthError(Exception):
    """Raised when Salesforce OAuth authentication fails."""


class SalesforceFetchError(Exception):
    """Raised when Salesforce SOQL query or record mapping fails."""


def _normalize_domain(domain: str) -> str:
    """Strip scheme/trailing slash from a Salesforce domain host."""
    value = domain.strip().removeprefix("https://").removeprefix("http://")
    return value.rstrip("/")


def get_salesforce_config() -> dict[str, str]:
    """Load Salesforce OAuth config from the environment.

    Returns:
        Dict with at least ``client_id``, ``client_secret``, and ``domain``.
        May also include ``username`` / ``password`` when set.

    Raises:
        SalesforceConfigError: If required env vars are missing or empty.
    """
    missing: list[str] = []
    values: dict[str, str] = {}
    for key in _REQUIRED_ENV_KEYS:
        value = (os.getenv(key) or "").strip()
        if not value:
            missing.append(key)
        else:
            values[key] = value

    if missing:
        raise SalesforceConfigError(
            "Missing Salesforce config: "
            + ", ".join(missing)
            + ". Set them in project/.env (see .env.example / README)."
        )

    config = {
        "client_id": values["SALESFORCE_CLIENT_ID"],
        "client_secret": values["SALESFORCE_CLIENT_SECRET"],
        "domain": _normalize_domain(values["SALESFORCE_DOMAIN"]),
    }
    username = (os.getenv("SALESFORCE_USERNAME") or "").strip()
    password = (os.getenv("SALESFORCE_PASSWORD") or "").strip()
    if username:
        config["username"] = username
    if password:
        config["password"] = password
    return config


def _token_url(domain: str) -> str:
    return f"https://{_normalize_domain(domain)}/services/oauth2/token"


def _authorize_url(domain: str) -> str:
    return f"https://{_normalize_domain(domain)}/services/oauth2/authorize"


def _save_token_payload(payload: dict[str, Any]) -> None:
    """Persist refresh_token / instance_url locally when the filesystem is writable.

    Skipped on Vercel / read-only serverless environments — use env vars there.
    """
    refresh_token = str(payload.get("refresh_token") or "").strip()
    instance_url = str(payload.get("instance_url") or "").strip()
    access_token = str(payload.get("access_token") or "").strip()
    if not refresh_token:
        return
    if os.getenv("VERCEL") or os.getenv("DISABLE_SALESFORCE_BROWSER_OAUTH"):
        return
    try:
        TOKEN_PATH.write_text(
            json.dumps(
                {
                    "refresh_token": refresh_token,
                    "instance_url": instance_url,
                    "access_token": access_token,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        # Read-only deploy filesystems (e.g. some serverless hosts).
        return


def _load_stored_refresh_token() -> tuple[str, str] | None:
    """Return ``(refresh_token, instance_url_hint)`` from env or token file."""
    env_refresh = (os.getenv("SALESFORCE_REFRESH_TOKEN") or "").strip()
    env_instance = (os.getenv("SALESFORCE_INSTANCE_URL") or "").strip()
    if env_refresh:
        return env_refresh, env_instance

    if not TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    refresh = str(data.get("refresh_token") or "").strip()
    instance = str(data.get("instance_url") or "").strip()
    if not refresh:
        return None
    return refresh, instance


def _post_token(domain: str, data: dict[str, str]) -> dict[str, Any]:
    """POST to the Salesforce token endpoint and return JSON."""
    try:
        response = requests.post(
            _token_url(domain),
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise SalesforceAuthError(
            f"Salesforce auth request failed: {exc}. "
            "Check SALESFORCE_DOMAIN and network connectivity."
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise SalesforceAuthError(
            "Salesforce auth returned a non-JSON response."
        ) from exc

    if not response.ok:
        error_desc = str(payload.get("error_description") or payload)
        raise SalesforceAuthError(f"Salesforce authentication failed: {error_desc}")

    return payload


# In-memory cache: refresh_token -> (access_token, instance_url, expires_at).
# Avoids re-refreshing on every serverless request (Salesforce may rotate refresh tokens).
_ACCESS_TOKEN_CACHE: dict[str, tuple[str, str, float]] = {}
_ACCESS_TOKEN_CACHE_TTL_SECONDS = 5400  # ~90 min; Salesforce access tokens last ~2 hours.


def _access_token_cache_key(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def _get_cached_access_token(refresh_token: str) -> tuple[str, str] | None:
    entry = _ACCESS_TOKEN_CACHE.get(_access_token_cache_key(refresh_token))
    if entry is None:
        return None
    access_token, instance_url, expires_at = entry
    if time.time() >= expires_at:
        return None
    return access_token, instance_url


def _set_cached_access_token(
    refresh_token: str,
    access_token: str,
    instance_url: str,
) -> None:
    _ACCESS_TOKEN_CACHE[_access_token_cache_key(refresh_token)] = (
        access_token,
        instance_url,
        time.time() + _ACCESS_TOKEN_CACHE_TTL_SECONDS,
    )


def _tokens_from_payload(
    payload: dict[str, Any],
    instance_hint: str = "",
) -> tuple[str, str]:
    """Extract access_token + instance_url from a token response."""
    access_token = str(payload.get("access_token") or "").strip()
    instance_url = str(payload.get("instance_url") or instance_hint or "").strip()
    if not access_token:
        raise SalesforceAuthError(
            "Salesforce auth response missing access_token."
        )
    if not instance_url:
        raise SalesforceAuthError(
            "Salesforce auth response missing instance_url. "
            "Set SALESFORCE_INSTANCE_URL in env."
        )
    return access_token, instance_url


def _refresh_access_token(
    config: dict[str, str],
    refresh_token: str,
    instance_hint: str = "",
) -> tuple[str, str]:
    """Exchange a refresh token for a new access token."""
    cached = _get_cached_access_token(refresh_token)
    if cached is not None:
        return cached

    payload = _post_token(
        config["domain"],
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        },
    )
    # Preserve refresh_token if Salesforce omits it on refresh responses.
    if not payload.get("refresh_token"):
        payload["refresh_token"] = refresh_token
    _save_token_payload(payload)
    access_token, instance_url = _tokens_from_payload(payload, instance_hint)
    _set_cached_access_token(refresh_token, access_token, instance_url)
    return access_token, instance_url


def _password_access_token(config: dict[str, str]) -> tuple[str, str]:
    """Authenticate via OAuth 2.0 Username-Password flow (org must allow it)."""
    username = config.get("username")
    password = config.get("password")
    if not username or not password:
        raise SalesforceAuthError(
            "Username/password auth requested but SALESFORCE_USERNAME / "
            "SALESFORCE_PASSWORD are not set."
        )

    try:
        payload = _post_token(
            config["domain"],
            {
                "grant_type": "password",
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "username": username,
                "password": password,
            },
        )
    except SalesforceAuthError as exc:
        raise SalesforceAuthError(
            f"{exc} "
            "If Username-Password flow is blocked in Setup > OAuth and OpenID "
            "Connect Settings, run a one-time browser login instead: "
            "`python3 -m integrations.salesforce_client login`. "
            "Also ensure Connected App callback URL includes "
            f"{get_redirect_uri()}."
        ) from exc

    _save_token_payload(payload)
    return _tokens_from_payload(payload)


def _generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for OAuth PKCE (S256)."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _build_authorization_login_url(config: dict[str, str]) -> tuple[str, str, str]:
    """Return ``(login_url, code_verifier, redirect_uri)`` for PKCE browser login."""
    code_verifier, code_challenge = _generate_pkce_pair()
    redirect_uri = get_redirect_uri()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "scope": "api refresh_token offline_access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    login_url = f"{_authorize_url(config['domain'])}?{query}"
    return login_url, code_verifier, redirect_uri


def _extract_authorization_code(raw: str) -> str:
    """Parse an OAuth authorization code from pasted text or a redirect URL."""
    text = raw.strip()
    if not text:
        raise SalesforceAuthError("No authorization code provided.")

    if "://" in text or text.startswith("?"):
        parsed = urlparse(text if "://" in text else f"http://local{text}")
        params = parse_qs(parsed.query)
        if params.get("error"):
            raise SalesforceAuthError(
                f"Salesforce browser login failed: "
                f"{params.get('error_description', params['error'])[0]}"
            )
        code = (params.get("code") or [""])[0].strip()
        if code:
            return code
        if parsed.path.rstrip("/").endswith("/callback") or "localhost" in text:
            raise SalesforceAuthError(
                "Redirect URL is missing ?code=.... "
                "After Salesforce login, the address bar should look like:\n"
                "  http://localhost:8765/callback?code=aPrx...\n"
                "Copy the entire URL including everything after ?code=, "
                "or paste only the code value."
            )

    if "code=" in text:
        parsed = urlparse(f"http://local?{text}")
        params = parse_qs(parsed.query)
        code = (params.get("code") or [""])[0].strip()
        if code:
            return code

    if text.startswith("http://") or text.startswith("https://"):
        raise SalesforceAuthError(
            "That URL does not contain an authorization code. "
            "Re-run login-manual, complete Salesforce login, and paste the "
            "full redirect URL with ?code=..."
        )

    return text


def _exchange_authorization_code(
    config: dict[str, str],
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> tuple[str, str]:
    """Exchange an authorization code for access + refresh tokens."""
    payload = _post_token(
        config["domain"],
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
    )
    if not payload.get("refresh_token"):
        raise SalesforceAuthError(
            "Salesforce did not return a refresh_token. In the Connected App, "
            "ensure selected OAuth scopes include refresh_token / offline_access, "
            "and Callback URL is exactly "
            f"{redirect_uri}."
        )
    _save_token_payload(payload)
    return _tokens_from_payload(payload)


def _save_pkce_state(code_verifier: str, redirect_uri: str) -> None:
    """Persist PKCE verifier so login can be completed in a separate step."""
    PKCE_STATE_PATH.write_text(
        json.dumps(
            {
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_pkce_state() -> tuple[str, str]:
    """Return ``(code_verifier, redirect_uri)`` from the last ``login-url`` run."""
    if not PKCE_STATE_PATH.exists():
        raise SalesforceAuthError(
            "Missing PKCE state. Run "
            "`python3 -m integrations.salesforce_client login-url` first."
        )
    try:
        data = json.loads(PKCE_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SalesforceAuthError(
            "Could not read PKCE state. Re-run login-url."
        ) from exc
    code_verifier = str(data.get("code_verifier") or "").strip()
    redirect_uri = str(data.get("redirect_uri") or "").strip()
    if not code_verifier or not redirect_uri:
        raise SalesforceAuthError(
            "PKCE state file is incomplete. Re-run login-url."
        )
    return code_verifier, redirect_uri


def login_salesforce_url_only() -> str:
    """Print a login URL and save PKCE state for a later ``login-exchange``."""
    config = get_salesforce_config()
    login_url, code_verifier, redirect_uri = _build_authorization_login_url(config)
    _save_pkce_state(code_verifier, redirect_uri)
    print("Open this URL in your browser and sign in to Salesforce:")
    print(login_url)
    print(
        "\nAfter login, copy the full redirect URL (with ?code=...) from the "
        "address bar, then run:\n"
        "  python3 -m integrations.salesforce_client login-exchange '<paste URL here>'"
    )
    return login_url


def login_salesforce_exchange(pasted: str) -> tuple[str, str]:
    """Exchange a pasted authorization code using saved PKCE state."""
    config = get_salesforce_config()
    code_verifier, redirect_uri = _load_pkce_state()
    code = _extract_authorization_code(pasted)
    return _exchange_authorization_code(
        config,
        code=code,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )


def login_salesforce_manual() -> tuple[str, str]:
    """Print a login URL and exchange a pasted authorization code (no local server)."""
    login_salesforce_url_only()
    pasted = input("Authorization code or redirect URL: ")
    return login_salesforce_exchange(pasted)


def _browser_authorization_code_login(config: dict[str, str]) -> tuple[str, str]:
    """Open a browser, capture the auth code on localhost, exchange for tokens."""
    cloud_host = bool(os.getenv("VERCEL") or os.getenv("DISABLE_SALESFORCE_BROWSER_OAUTH"))
    if cloud_host:
        raise SalesforceAuthError(
            "Missing Salesforce refresh token for cloud deploy. "
            "Set SALESFORCE_REFRESH_TOKEN (and optionally SALESFORCE_INSTANCE_URL) "
            "from a local `python3 -m integrations.salesforce_client login` run."
        )

    auth_code: dict[str, str] = {}
    error_holder: dict[str, str] = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(parsed.query)
            if params.get("error"):
                error_holder["error"] = params.get("error_description", params["error"])[0]
            else:
                code = (params.get("code") or [""])[0]
                if code:
                    auth_code["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Salesforce login complete.</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    code_verifier, code_challenge = _generate_pkce_pair()
    redirect_uri = get_redirect_uri()

    query = urlencode(
        {
            "response_type": "code",
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "scope": "api refresh_token offline_access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    login_url = f"{_authorize_url(config['domain'])}?{query}"

    try:
        class _ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        server = _ReusableHTTPServer(
            (LOCAL_CALLBACK_HOST, LOCAL_CALLBACK_PORT), _Handler
        )
    except OSError as exc:
        if getattr(exc, "errno", None) == 98:
            raise SalesforceAuthError(
                f"OAuth callback port {LOCAL_CALLBACK_PORT} is already in use. "
                "Stop the other process, or run: "
                "`python3 -m integrations.salesforce_client login-manual`"
            ) from exc
        raise

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"Opening Salesforce login in your browser...\n{login_url}")
    webbrowser.open(login_url)
    thread.join(timeout=180)
    server.server_close()

    if error_holder.get("error"):
        raise SalesforceAuthError(
            f"Salesforce browser login failed: {error_holder['error']}"
        )
    if not auth_code.get("code"):
        raise SalesforceAuthError(
            "Salesforce browser login timed out or returned no authorization code. "
            f"Confirm Connected App Callback URL includes {redirect_uri}. "
            "If localhost callback is blocked, run login-manual instead."
        )

    return _exchange_authorization_code(
        config,
        code=auth_code["code"],
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )


def login_salesforce_interactive() -> tuple[str, str]:
    """Force a browser login and save the refresh token for later API calls."""
    config = get_salesforce_config()
    return _browser_authorization_code_login(config)


def get_salesforce_access_token(*, allow_browser: bool = False) -> tuple[str, str]:
    """Return ``(access_token, instance_url)`` using refresh token when possible.

    Preference order:
    1. Refresh token (env / ``salesforce_token.json``)
    2. Username-Password flow (if username + password are configured)
    3. Interactive browser Authorization Code flow — **only** when
       ``allow_browser=True`` (CLI ``login``). API / dashboard paths never open
       a browser (avoids port-8765 conflicts and 502s under concurrent load).

    Raises:
        SalesforceConfigError: When required Connected App settings are missing.
        SalesforceAuthError: When Salesforce rejects authentication.
    """
    config = get_salesforce_config()
    cloud_host = bool(
        os.getenv("VERCEL") or os.getenv("DISABLE_SALESFORCE_BROWSER_OAUTH")
    )

    stored = _load_stored_refresh_token()
    if stored is not None:
        refresh_token, instance_hint = stored
        try:
            return _refresh_access_token(config, refresh_token, instance_hint)
        except SalesforceAuthError as refresh_exc:
            if cloud_host or not allow_browser:
                raise SalesforceAuthError(
                    f"{refresh_exc} "
                    "Refresh token is expired or was invalidated (common if someone "
                    "ran `python3 -m integrations.salesforce_client login` on another "
                    "machine — Salesforce may rotate/revoke the previous refresh token). "
                    "Fix on ONE machine only: "
                    "`python3 -m integrations.salesforce_client login` "
                    "(or `login-manual` if port 8765 is busy) "
                    "then `./scripts/sync_salesforce_token_to_vercel.sh`."
                ) from refresh_exc
            # Local CLI with allow_browser: fall through to password / browser login.

    if config.get("username") and config.get("password"):
        try:
            return _password_access_token(config)
        except SalesforceAuthError as exc:
            if cloud_host or not allow_browser:
                raise
            print(f"Username-Password auth failed ({exc}); trying browser login...")

    if allow_browser and not cloud_host:
        return _browser_authorization_code_login(config)

    raise SalesforceAuthError(
        "Salesforce auth failed and interactive browser login is disabled for API "
        "requests. Run locally: `python3 -m integrations.salesforce_client login` "
        "(or `login-manual` if port 8765 is in use), then "
        "`./scripts/sync_salesforce_token_to_vercel.sh`."
    )


def _parse_approved_date(value: Any, project_id: str) -> datetime:
    """Parse Salesforce date (YYYY-MM-DD) into a timezone-aware datetime."""
    if not value:
        raise SalesforceFetchError(
            f"Missing Approved_Date__c for project '{project_id}'."
        )
    text = str(value).strip()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise SalesforceFetchError(
            f"Could not parse Approved_Date__c for project '{project_id}': {text!r}."
        ) from exc


def _record_to_project_approval(record: dict[str, Any]) -> ProjectApproval:
    """Convert one Salesforce Approved_Project__c record into ProjectApproval."""
    project_id = str(record.get("Name") or "").strip()
    if not project_id:
        raise SalesforceFetchError(
            "Salesforce record is missing Name (project_id)."
        )

    client_name = str(record.get("Client_Name__c") or "").strip()
    vendor_name = str(record.get("Vendor_Name__c") or "").strip()
    if not client_name:
        raise SalesforceFetchError(
            f"Missing Client_Name__c for project '{project_id}'."
        )
    if not vendor_name:
        raise SalesforceFetchError(
            f"Missing Vendor_Name__c for project '{project_id}'."
        )

    if "PO_Exists__c" not in record:
        raise SalesforceFetchError(
            f"Missing PO_Exists__c for project '{project_id}'."
        )

    po_exists = bool(record.get("PO_Exists__c"))
    amount_raw = record.get("Estimated_Amount__c")
    try:
        estimated_amount = 0.0 if amount_raw is None else float(amount_raw)
    except (TypeError, ValueError) as exc:
        raise SalesforceFetchError(
            f"Invalid Estimated_Amount__c for project '{project_id}': {amount_raw!r}."
        ) from exc

    return ProjectApproval(
        project_id=project_id,
        client_name=client_name,
        approved_at=_parse_approved_date(record.get("Approved_Date__c"), project_id),
        po_exists=po_exists,
        estimated_amount=estimated_amount,
        vendor_name=vendor_name,
        salesforce_id=str(record.get("Id") or "").strip() or None,
    )


def fetch_approved_projects(
    access_token: str | None = None,
    instance_url: str | None = None,
) -> list[ProjectApproval]:
    """Fetch approved projects from Salesforce via SOQL (read-only).

    Args:
        access_token: Optional OAuth access token; obtained automatically if omitted.
        instance_url: Optional Salesforce instance URL; obtained with the token.

    Returns:
        Parsed ``ProjectApproval`` objects for ``POAutomationAgent``.

    Raises:
        SalesforceConfigError: If credentials are not configured.
        SalesforceAuthError: If OAuth login fails.
        SalesforceFetchError: On query or mapping failures.
    """
    if access_token is None or instance_url is None:
        access_token, instance_url = get_salesforce_access_token()

    query_url = (
        f"{instance_url.rstrip('/')}/services/data/{API_VERSION}/query/"
        f"?q={quote(_SOQL_QUERY)}"
    )

    try:
        response = requests.get(
            query_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise SalesforceFetchError(
            f"Salesforce query request failed: {exc}."
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise SalesforceFetchError(
            "Salesforce query returned a non-JSON response."
        ) from exc

    if not response.ok:
        message = payload
        if isinstance(payload, list) and payload:
            message = payload[0].get("message", payload)
        elif isinstance(payload, dict):
            message = payload.get("message") or payload.get("error") or payload
        raise SalesforceFetchError(f"Salesforce SOQL query failed: {message}")

    records = payload.get("records")
    if not isinstance(records, list):
        raise SalesforceFetchError(
            "Salesforce query response missing records list."
        )

    try:
        return [_record_to_project_approval(record) for record in records]
    except (SalesforceConfigError, SalesforceAuthError, SalesforceFetchError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise SalesforceFetchError(
            f"Salesforce integration failed while mapping records: {exc}."
        ) from exc


def create_record(
    object_api_name: str,
    fields: dict[str, Any],
    *,
    access_token: str | None = None,
    instance_url: str | None = None,
) -> dict[str, Any]:
    """Create a Salesforce sObject via REST POST.

    Returns:
        Dict with at least ``id`` and ``success`` from Salesforce.
    """
    if access_token is None or instance_url is None:
        access_token, instance_url = get_salesforce_access_token()

    url = (
        f"{instance_url.rstrip('/')}/services/data/{API_VERSION}/sobjects/"
        f"{object_api_name}/"
    )
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=fields,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise SalesforceFetchError(f"Salesforce create failed: {exc}.") from exc

    try:
        payload = response.json() if response.content else {}
    except ValueError as exc:
        raise SalesforceFetchError(
            "Salesforce create returned a non-JSON response."
        ) from exc

    if not response.ok:
        raise SalesforceFetchError(f"Salesforce create failed: {payload}")

    return {
        "id": payload.get("id") if isinstance(payload, dict) else None,
        "success": True,
        "object": object_api_name,
        "fields": fields,
    }


def update_record(
    object_api_name: str,
    record_id: str,
    fields: dict[str, Any],
    *,
    access_token: str | None = None,
    instance_url: str | None = None,
) -> dict[str, Any]:
    """Update a Salesforce sObject via REST PATCH."""
    if access_token is None or instance_url is None:
        access_token, instance_url = get_salesforce_access_token()

    url = (
        f"{instance_url.rstrip('/')}/services/data/{API_VERSION}/sobjects/"
        f"{object_api_name}/{record_id}"
    )
    try:
        response = requests.patch(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=fields,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise SalesforceFetchError(f"Salesforce update failed: {exc}.") from exc

    if response.status_code not in {204, 200}:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        raise SalesforceFetchError(f"Salesforce update failed: {payload}")

    return {
        "id": record_id,
        "success": True,
        "object": object_api_name,
        "fields": fields,
    }


def _print_login_success(token: str, instance_url: str) -> None:
    print("Login OK.")
    print(f"Instance: {instance_url}")
    print(f"Token saved to: {TOKEN_PATH}")
    print(f"Access token prefix: {token[:12]}...")
    print(
        "\nNext: sync to Vercel without running other Salesforce auth locally:\n"
        "  ./scripts/sync_salesforce_token_to_vercel.sh"
    )


def main() -> None:
    """CLI helper for Salesforce OAuth login."""
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "login-url":
            login_salesforce_url_only()
            return
        if cmd == "login-exchange":
            if len(sys.argv) < 3:
                raise SystemExit(
                    "Usage: python3 -m integrations.salesforce_client "
                    "login-exchange '<redirect URL or code>'"
                )
            token, instance_url = login_salesforce_exchange(sys.argv[2])
            _print_login_success(token, instance_url)
            return
        if cmd in {"login", "login-manual"}:
            if cmd == "login-manual":
                token, instance_url = login_salesforce_manual()
            else:
                try:
                    token, instance_url = login_salesforce_interactive()
                except SalesforceAuthError as exc:
                    if "already in use" in str(exc):
                        print(f"{exc}\n")
                        token, instance_url = login_salesforce_manual()
                    else:
                        raise
            _print_login_success(token, instance_url)
            return

    print("Usage:")
    print("  python3 -m integrations.salesforce_client login")
    print("  python3 -m integrations.salesforce_client login-manual")
    print("  python3 -m integrations.salesforce_client login-url")
    print("  python3 -m integrations.salesforce_client login-exchange '<URL or code>'")


if __name__ == "__main__":
    main()
