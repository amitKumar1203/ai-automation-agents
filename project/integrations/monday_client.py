"""Monday.com API client for vendor quote requests.

Fetches board items by default. Mutations (status updates) run only when
post-approval write-back is enabled (``WRITE_BACK_MODE=live``).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from models.task import VendorQuoteRequest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = _PROJECT_ROOT / ".env"
MONDAY_API_URL = "https://api.monday.com/v2"
REQUEST_TIMEOUT_SECONDS = 10
ITEMS_PAGE_LIMIT = 500

# Column titles expected on the "Vendor Requests" board.
COLUMN_PROJECT_ID = "Project ID"
COLUMN_QUOTE_RECEIVED = "Quote Received"
COLUMN_REQUEST_SENT_DATE = "Request Sent Date"
COLUMN_BUDGET = "Budget"

_REQUIRED_COLUMN_TITLES = (
    COLUMN_PROJECT_ID,
    COLUMN_QUOTE_RECEIVED,
    COLUMN_REQUEST_SENT_DATE,
)

_BOARD_QUERY = """
query ($boardId: [ID!], $limit: Int!) {
  boards(ids: $boardId) {
    columns {
      id
      title
    }
    items_page(limit: $limit) {
      items {
        id
        name
        column_values {
          id
          text
          value
        }
      }
    }
  }
}
"""

load_dotenv(ENV_PATH)


class MondayConfigError(Exception):
    """Raised when Monday.com credentials or board ID are missing."""


class MondayFetchError(Exception):
    """Raised when Monday.com authentication or fetch fails."""


def get_monday_api_token() -> str:
    """Return the Monday.com API token from the environment.

    Raises:
        MondayConfigError: If ``MONDAY_API_TOKEN`` is missing or empty.
    """
    token = (os.getenv("MONDAY_API_TOKEN") or "").strip()
    if not token:
        raise MondayConfigError(
            "Missing MONDAY_API_TOKEN. Set it in project/.env (see README)."
        )
    return token


def get_monday_board_id() -> str:
    """Return the Monday.com board ID from the environment.

    Raises:
        MondayConfigError: If ``MONDAY_BOARD_ID`` is missing or empty.
    """
    board_id = (os.getenv("MONDAY_BOARD_ID") or "").strip()
    if not board_id:
        raise MondayConfigError(
            "Missing MONDAY_BOARD_ID. Set it in project/.env (see README)."
        )
    return board_id


def _post_graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """Execute a GraphQL query against the Monday.com API."""
    token = get_monday_api_token()
    try:
        response = requests.post(
            MONDAY_API_URL,
            json={"query": query, "variables": variables},
            headers={
                "Authorization": token,
                "Content-Type": "application/json",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MondayFetchError(
            f"Monday.com API request failed: {exc}. "
            "Check MONDAY_API_TOKEN and network connectivity."
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise MondayFetchError(
            "Monday.com API returned a non-JSON response."
        ) from exc

    if payload.get("errors"):
        messages = "; ".join(
            str(error.get("message", error)) for error in payload["errors"]
        )
        raise MondayFetchError(f"Monday.com GraphQL error: {messages}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise MondayFetchError("Monday.com API response missing data payload.")

    return data


def _column_map(columns: list[dict[str, Any]]) -> dict[str, str]:
    """Map column title -> column id for required board columns."""
    title_to_id = {
        str(column.get("title", "")).strip(): str(column.get("id", ""))
        for column in columns
        if column.get("id")
    }
    missing = [
        title for title in _REQUIRED_COLUMN_TITLES if title not in title_to_id
    ]
    if missing:
        raise MondayFetchError(
            "Monday.com board is missing required columns: "
            + ", ".join(missing)
            + ". Expected titles: "
            + ", ".join(_REQUIRED_COLUMN_TITLES)
            + f" (and optionally {COLUMN_BUDGET})."
        )
    return title_to_id


def _column_value_by_id(
    column_values: list[dict[str, Any]], column_id: str
) -> dict[str, str]:
    """Return ``text`` and ``value`` for a column id (empty strings if absent)."""
    for column_value in column_values:
        if str(column_value.get("id", "")) == column_id:
            return {
                "text": str(column_value.get("text") or "").strip(),
                "value": str(column_value.get("value") or "").strip(),
            }
    return {"text": "", "value": ""}


def _parse_request_sent_date(text: str, raw_value: str, vendor_name: str) -> datetime:
    """Parse Monday.com date column into a timezone-aware datetime (UTC)."""
    if raw_value:
        try:
            parsed = json.loads(raw_value)
            date_str = str(parsed.get("date") or "").strip()
            time_str = str(parsed.get("time") or "").strip()
            if date_str and time_str:
                return datetime.fromisoformat(f"{date_str}T{time_str}").replace(
                    tzinfo=timezone.utc
                )
            if date_str:
                return datetime.strptime(date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    if text:
        try:
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    raise MondayFetchError(
        f"Could not parse Request Sent Date for vendor '{vendor_name}'. "
        f"Expected YYYY-MM-DD, got text={text!r} value={raw_value!r}."
    )


def _item_to_vendor_request(
    item: dict[str, Any],
    title_to_id: dict[str, str],
) -> VendorQuoteRequest:
    """Convert one Monday.com board item into a ``VendorQuoteRequest``."""
    vendor_name = str(item.get("name") or "").strip()
    if not vendor_name:
        raise MondayFetchError("Monday.com item is missing a vendor name (item name).")

    column_values = item.get("column_values") or []
    if not isinstance(column_values, list):
        raise MondayFetchError(
            f"Malformed column_values for vendor '{vendor_name}'."
        )

    project_id_col = _column_value_by_id(
        column_values, title_to_id[COLUMN_PROJECT_ID]
    )
    quote_col = _column_value_by_id(
        column_values, title_to_id[COLUMN_QUOTE_RECEIVED]
    )
    date_col = _column_value_by_id(
        column_values, title_to_id[COLUMN_REQUEST_SENT_DATE]
    )

    project_id = project_id_col["text"]
    if not project_id:
        raise MondayFetchError(
            f"Missing Project ID for vendor '{vendor_name}' on Monday.com board."
        )

    quote_status = quote_col["text"]
    if not quote_status:
        raise MondayFetchError(
            f"Missing Quote Received status for vendor '{vendor_name}'."
        )

    request_sent_at = _parse_request_sent_date(
        date_col["text"],
        date_col["value"],
        vendor_name,
    )

    monday_item_id = str(item.get("id") or "").strip() or None

    return VendorQuoteRequest(
        vendor_name=vendor_name,
        project_id=project_id,
        request_sent_at=request_sent_at,
        quote_received=quote_status == "Received",
        quote_received_at=None,
        monday_item_id=monday_item_id,
    )


def fetch_vendor_requests() -> list[VendorQuoteRequest]:
    """Fetch all vendor quote requests from the configured Monday.com board.

    Returns:
        Parsed ``VendorQuoteRequest`` objects ready for ``VendorFollowUpAgent``.

    Raises:
        MondayConfigError: If API token or board ID is not configured.
        MondayFetchError: On network, auth, or malformed board/item errors.
    """
    board_id = get_monday_board_id()

    try:
        data = _post_graphql(
            _BOARD_QUERY,
            {"boardId": [board_id], "limit": ITEMS_PAGE_LIMIT},
        )
        boards = data.get("boards") or []
        if not boards:
            raise MondayFetchError(
                f"Monday.com board {board_id!r} was not found or is not accessible."
            )

        board = boards[0]
        columns = board.get("columns") or []
        if not isinstance(columns, list):
            raise MondayFetchError("Monday.com board columns payload is malformed.")

        title_to_id = _column_map(columns)

        items_page = board.get("items_page") or {}
        items = items_page.get("items") or []
        if not isinstance(items, list):
            raise MondayFetchError("Monday.com board items payload is malformed.")

        return [_item_to_vendor_request(item, title_to_id) for item in items]
    except (MondayConfigError, MondayFetchError):
        raise
    except Exception as exc:  # noqa: BLE001 — surface as a clear Monday error
        raise MondayFetchError(
            f"Monday.com integration failed: {exc}. "
            "Check MONDAY_API_TOKEN, MONDAY_BOARD_ID, and board column titles."
        ) from exc


_CHANGE_STATUS_MUTATION = """
mutation ($boardId: ID!, $itemId: ID!, $columnId: String!, $value: JSON!) {
  change_column_value(
    board_id: $boardId,
    item_id: $itemId,
    column_id: $columnId,
    value: $value
  ) {
    id
  }
}
"""


def _fetch_board_column_map() -> dict[str, str]:
    """Return title -> column id map for the configured board."""
    board_id = get_monday_board_id()
    data = _post_graphql(
        """
        query ($boardId: [ID!]) {
          boards(ids: $boardId) {
            columns { id title }
          }
        }
        """,
        {"boardId": [board_id]},
    )
    boards = data.get("boards") or []
    if not boards:
        raise MondayFetchError(f"Monday.com board {board_id!r} was not found.")
    columns = boards[0].get("columns") or []
    return _column_map(columns)


def update_status_column_by_title(
    *,
    item_id: str,
    column_title: str,
    label: str,
) -> dict[str, Any]:
    """Update a Monday.com status column by visible label text.

    Uses ``change_column_value`` with ``{"label": "<label>"}`` JSON.
    Requires a Monday API token with write access to the board.
    """
    board_id = get_monday_board_id()
    title_to_id = _fetch_board_column_map()
    if column_title not in title_to_id:
        raise MondayFetchError(
            f"Column title {column_title!r} not found on board {board_id}."
        )
    column_id = title_to_id[column_title]
    value_json = json.dumps({"label": label})

    data = _post_graphql(
        _CHANGE_STATUS_MUTATION,
        {
            "boardId": board_id,
            "itemId": item_id,
            "columnId": column_id,
            "value": value_json,
        },
    )
    changed = (data.get("change_column_value") or {}).get("id")
    return {
        "item_id": item_id,
        "column_id": column_id,
        "label": label,
        "changed_item_id": changed,
    }


def find_item_id_by_project_id(project_id: str) -> str | None:
    """Return the Monday item id whose Project ID column matches ``project_id``."""
    board_id = get_monday_board_id()
    data = _post_graphql(
        _BOARD_QUERY,
        {"boardId": [board_id], "limit": ITEMS_PAGE_LIMIT},
    )
    boards = data.get("boards") or []
    if not boards:
        raise MondayFetchError(f"Monday.com board {board_id!r} was not found.")
    board = boards[0]
    title_to_id = _column_map(board.get("columns") or [])
    project_col_id = title_to_id[COLUMN_PROJECT_ID]
    items = (board.get("items_page") or {}).get("items") or []
    needle = str(project_id).strip()
    for item in items:
        values = item.get("column_values") or []
        text = _column_value_by_id(values, project_col_id)["text"]
        if text == needle:
            item_id = str(item.get("id") or "").strip()
            return item_id or None
    return None


def update_text_column_by_title(
    *,
    item_id: str,
    column_title: str,
    text: str,
) -> dict[str, Any]:
    """Set a Monday text/name column value (JSON-encoded string)."""
    board_id = get_monday_board_id()
    # Use a permissive column map (not only required vendor columns).
    data = _post_graphql(
        """
        query ($boardId: [ID!]) {
          boards(ids: $boardId) {
            columns { id title }
          }
        }
        """,
        {"boardId": [board_id]},
    )
    boards = data.get("boards") or []
    if not boards:
        raise MondayFetchError(f"Monday.com board {board_id!r} was not found.")
    title_to_id = {
        str(column.get("title", "")).strip(): str(column.get("id", ""))
        for column in (boards[0].get("columns") or [])
        if column.get("id")
    }
    if column_title not in title_to_id:
        raise MondayFetchError(
            f"Column title {column_title!r} not found on board {board_id}."
        )
    column_id = title_to_id[column_title]
    value_json = json.dumps(text)
    result = _post_graphql(
        _CHANGE_STATUS_MUTATION,
        {
            "boardId": board_id,
            "itemId": item_id,
            "columnId": column_id,
            "value": value_json,
        },
    )
    changed = (result.get("change_column_value") or {}).get("id")
    return {
        "item_id": item_id,
        "column_id": column_id,
        "text": text,
        "changed_item_id": changed,
    }


def sync_po_number_to_monday(
    *,
    project_id: str,
    po_number: str,
    column_title: str | None = None,
) -> dict[str, Any]:
    """Find the Monday item for ``project_id`` and write the PO number.

    Column title defaults to env ``MONDAY_PO_COLUMN_TITLE`` or ``PO Number``.
    """
    title = (
        column_title
        or (os.getenv("MONDAY_PO_COLUMN_TITLE") or "").strip()
        or "PO Number"
    )
    item_id = find_item_id_by_project_id(project_id)
    if not item_id:
        return {
            "skipped": True,
            "reason": f"No Monday item with Project ID={project_id!r}",
            "project_id": project_id,
            "po_number": po_number,
        }
    updated = update_text_column_by_title(
        item_id=item_id,
        column_title=title,
        text=po_number,
    )
    return {
        "project_id": project_id,
        "po_number": po_number,
        "column_title": title,
        **updated,
    }
