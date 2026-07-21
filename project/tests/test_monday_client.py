"""Tests for the read-only Monday.com client (mocked HTTP — no live API calls)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from integrations.monday_client import (
    MondayConfigError,
    MondayFetchError,
    fetch_vendor_requests,
    get_monday_api_token,
    get_monday_board_id,
)


def _board_payload(items: list[dict]) -> dict:
    """Build a minimal Monday.com GraphQL ``data`` payload."""
    return {
        "boards": [
            {
                "columns": [
                    {"id": "col_project", "title": "Project ID"},
                    {"id": "col_quote", "title": "Quote Received"},
                    {"id": "col_date", "title": "Request Sent Date"},
                    {"id": "col_budget", "title": "Budget"},
                ],
                "items_page": {"items": items},
            }
        ]
    }


def _item(
    name: str,
    project_id: str,
    quote_status: str,
    sent_date: str = "2026-07-01",
    item_id: str = "item-1",
) -> dict:
    return {
        "id": item_id,
        "name": name,
        "column_values": [
            {
                "id": "col_project",
                "text": project_id,
                "value": f'"{project_id}"',
            },
            {
                "id": "col_quote",
                "text": quote_status,
                "value": '{"index":1}',
            },
            {
                "id": "col_date",
                "text": sent_date,
                "value": f'{{"date":"{sent_date}","time":null}}',
            },
            {
                "id": "col_budget",
                "text": "5000",
                "value": "5000",
            },
        ],
    }


def _mock_post_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


@patch("integrations.monday_client.requests.post")
def test_fetch_vendor_requests_parses_items(mock_post: MagicMock) -> None:
    """Successful board response maps items into VendorQuoteRequest objects."""
    mock_post.return_value = _mock_post_response(
        {
            "data": _board_payload(
                [
                    _item("Acme Supplies", "PRJ-2001", "Pending", "2026-07-01"),
                    _item("Omega Parts Co", "PRJ-2002", "Received", "2026-06-15"),
                    _item("Delta Components", "PRJ-2003", "Escalate", "2026-05-20"),
                ]
            )
        }
    )

    with patch.dict(
        "os.environ",
        {"MONDAY_API_TOKEN": "token", "MONDAY_BOARD_ID": "12345"},
        clear=False,
    ):
        results = fetch_vendor_requests()

    assert len(results) == 3
    assert results[0].vendor_name == "Acme Supplies"
    assert results[0].project_id == "PRJ-2001"
    assert results[0].quote_received is False
    assert results[0].quote_received_at is None
    assert results[0].request_sent_at == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert results[0].monday_item_id == "item-1"

    assert results[1].vendor_name == "Omega Parts Co"
    assert results[1].project_id == "PRJ-2002"
    assert results[1].quote_received is True

    assert results[2].vendor_name == "Delta Components"
    assert results[2].project_id == "PRJ-2003"
    assert results[2].quote_received is False


@patch("integrations.monday_client.requests.post")
def test_quote_received_status_mapping(mock_post: MagicMock) -> None:
    """Only the exact 'Received' label sets quote_received=True."""
    mock_post.return_value = _mock_post_response(
        {
            "data": _board_payload(
                [
                    _item("Vendor A", "PRJ-A", "Received"),
                    _item("Vendor B", "PRJ-B", "Pending"),
                    _item("Vendor C", "PRJ-C", "Escalate"),
                ]
            )
        }
    )

    with patch.dict(
        "os.environ",
        {"MONDAY_API_TOKEN": "token", "MONDAY_BOARD_ID": "12345"},
        clear=False,
    ):
        results = fetch_vendor_requests()

    by_project = {item.project_id: item for item in results}
    assert by_project["PRJ-A"].quote_received is True
    assert by_project["PRJ-B"].quote_received is False
    assert by_project["PRJ-C"].quote_received is False


@patch("integrations.monday_client.requests.post")
def test_missing_required_column_raises_fetch_error(mock_post: MagicMock) -> None:
    """Missing board columns should raise MondayFetchError with a clear message."""
    mock_post.return_value = _mock_post_response(
        {
            "data": {
                "boards": [
                    {
                        "columns": [{"id": "col_project", "title": "Project ID"}],
                        "items_page": {"items": []},
                    }
                ]
            }
        }
    )

    with patch.dict(
        "os.environ",
        {"MONDAY_API_TOKEN": "token", "MONDAY_BOARD_ID": "12345"},
        clear=False,
    ):
        with pytest.raises(MondayFetchError, match="missing required columns"):
            fetch_vendor_requests()


@patch("integrations.monday_client.requests.post")
def test_malformed_item_data_raises_fetch_error(mock_post: MagicMock) -> None:
    """Items missing Project ID should raise MondayFetchError cleanly."""
    mock_post.return_value = _mock_post_response(
        {
            "data": _board_payload(
                [
                    {
                        "name": "Broken Vendor",
                        "column_values": [
                            {
                                "id": "col_project",
                                "text": "",
                                "value": "",
                            },
                            {
                                "id": "col_quote",
                                "text": "Pending",
                                "value": "{}",
                            },
                            {
                                "id": "col_date",
                                "text": "2026-07-01",
                                "value": '{"date":"2026-07-01","time":null}',
                            },
                        ],
                    }
                ]
            )
        }
    )

    with patch.dict(
        "os.environ",
        {"MONDAY_API_TOKEN": "token", "MONDAY_BOARD_ID": "12345"},
        clear=False,
    ):
        with pytest.raises(MondayFetchError, match="Missing Project ID"):
            fetch_vendor_requests()


@patch("integrations.monday_client.requests.post")
def test_network_error_raises_fetch_error(mock_post: MagicMock) -> None:
    """Network failures should be wrapped as MondayFetchError."""
    mock_post.side_effect = requests.Timeout("timed out")

    with patch.dict(
        "os.environ",
        {"MONDAY_API_TOKEN": "token", "MONDAY_BOARD_ID": "12345"},
        clear=False,
    ):
        with pytest.raises(MondayFetchError, match="API request failed"):
            fetch_vendor_requests()


def test_missing_api_token_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing MONDAY_API_TOKEN should raise MondayConfigError."""
    monkeypatch.delenv("MONDAY_API_TOKEN", raising=False)
    monkeypatch.setenv("MONDAY_BOARD_ID", "12345")

    with pytest.raises(MondayConfigError, match="MONDAY_API_TOKEN"):
        get_monday_api_token()


def test_missing_board_id_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing MONDAY_BOARD_ID should raise MondayConfigError."""
    monkeypatch.setenv("MONDAY_API_TOKEN", "token")
    monkeypatch.delenv("MONDAY_BOARD_ID", raising=False)

    with pytest.raises(MondayConfigError, match="MONDAY_BOARD_ID"):
        get_monday_board_id()
