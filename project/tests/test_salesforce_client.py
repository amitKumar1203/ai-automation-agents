"""Tests for the read-only Salesforce client (mocked HTTP — no live API calls)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from integrations.salesforce_client import (
    SalesforceAuthError,
    SalesforceConfigError,
    SalesforceFetchError,
    _ACCESS_TOKEN_CACHE,
    fetch_approved_projects,
    get_salesforce_access_token,
    get_salesforce_config,
)

_ENV = {
    "SALESFORCE_CLIENT_ID": "client-id",
    "SALESFORCE_CLIENT_SECRET": "client-secret",
    "SALESFORCE_USERNAME": "user@example.com",
    "SALESFORCE_PASSWORD": "secret",
    "SALESFORCE_DOMAIN": "login.salesforce.com",
}


def _record(
    *,
    name: str,
    client: str,
    vendor: str,
    approved_date: str,
    po_exists: bool,
    amount: float | None,
    record_id: str = "a00TEST000000001",
) -> dict:
    return {
        "Id": record_id,
        "Name": name,
        "Client_Name__c": client,
        "Vendor_Name__c": vendor,
        "Approved_Date__c": approved_date,
        "PO_Exists__c": po_exists,
        "Estimated_Amount__c": amount,
    }


@pytest.fixture(autouse=True)
def _clear_refresh_token_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Avoid picking up a real local refresh token during unit tests."""
    monkeypatch.delenv("SALESFORCE_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("SALESFORCE_INSTANCE_URL", raising=False)
    monkeypatch.setenv("DISABLE_SALESFORCE_BROWSER_OAUTH", "1")
    monkeypatch.setattr(
        "integrations.salesforce_client.TOKEN_PATH",
        tmp_path / "salesforce_token.json",
    )
    _ACCESS_TOKEN_CACHE.clear()


def test_get_salesforce_config_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Required Connected App env vars should load into a config dict."""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)

    config = get_salesforce_config()
    assert config["client_id"] == "client-id"
    assert config["username"] == "user@example.com"
    assert config["domain"] == "login.salesforce.com"


def test_missing_env_vars_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Connected App credentials should raise SalesforceConfigError."""
    for key in (
        "SALESFORCE_CLIENT_ID",
        "SALESFORCE_CLIENT_SECRET",
        "SALESFORCE_DOMAIN",
        "SALESFORCE_USERNAME",
        "SALESFORCE_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(SalesforceConfigError, match="Missing Salesforce config"):
        get_salesforce_config()


@patch("integrations.salesforce_client.requests.post")
def test_get_access_token_success(
    mock_post: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful password-auth response returns access_token and instance_url."""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)

    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "access_token": "tok-123",
        "instance_url": "https://example.my.salesforce.com",
    }
    mock_post.return_value = response

    token, instance_url = get_salesforce_access_token()
    assert token == "tok-123"
    assert instance_url == "https://example.my.salesforce.com"
    mock_post.assert_called_once()


@patch("integrations.salesforce_client.requests.post")
def test_refresh_token_auth_success(
    mock_post: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored refresh token should be preferred over username/password."""
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", "client-id")
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("SALESFORCE_DOMAIN", "login.salesforce.com")
    monkeypatch.setenv("SALESFORCE_REFRESH_TOKEN", "refresh-abc")

    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "access_token": "tok-from-refresh",
        "instance_url": "https://example.my.salesforce.com",
    }
    mock_post.return_value = response

    token, instance_url = get_salesforce_access_token()
    assert token == "tok-from-refresh"
    assert instance_url == "https://example.my.salesforce.com"
    assert mock_post.call_args.kwargs["data"]["grant_type"] == "refresh_token"


@patch("integrations.salesforce_client.requests.post")
def test_expired_refresh_token_falls_back_to_password_locally(
    mock_post: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When refresh fails locally, username-password auth should still be tried."""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SALESFORCE_REFRESH_TOKEN", "refresh-abc")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("DISABLE_SALESFORCE_BROWSER_OAUTH", raising=False)

    refresh_fail = MagicMock()
    refresh_fail.ok = False
    refresh_fail.json.return_value = {
        "error": "invalid_grant",
        "error_description": "expired access/refresh token",
    }
    password_ok = MagicMock()
    password_ok.ok = True
    password_ok.json.return_value = {
        "access_token": "tok-from-password",
        "instance_url": "https://example.my.salesforce.com",
        "refresh_token": "refresh-new",
    }
    mock_post.side_effect = [refresh_fail, password_ok]

    token, instance_url = get_salesforce_access_token()

    assert token == "tok-from-password"
    assert instance_url == "https://example.my.salesforce.com"
    assert mock_post.call_count == 2
    assert mock_post.call_args_list[1].kwargs["data"]["grant_type"] == "password"


@patch("integrations.salesforce_client.requests.post")
def test_expired_refresh_token_raises_on_cloud_without_password_fallback(
    mock_post: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vercel should not silently fall back when refresh token is invalid."""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SALESFORCE_REFRESH_TOKEN", "refresh-abc")
    monkeypatch.setenv("VERCEL", "1")

    response = MagicMock()
    response.ok = False
    response.json.return_value = {
        "error": "invalid_grant",
        "error_description": "expired access/refresh token",
    }
    mock_post.return_value = response

    with pytest.raises(SalesforceAuthError, match="expired access/refresh token"):
        get_salesforce_access_token()

    mock_post.assert_called_once()


@patch("integrations.salesforce_client.requests.post")
def test_refresh_token_uses_instance_url_env_hint(
    mock_post: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh responses without instance_url should fall back to env hint."""
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", "client-id")
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("SALESFORCE_DOMAIN", "login.salesforce.com")
    monkeypatch.setenv("SALESFORCE_REFRESH_TOKEN", "refresh-abc")
    monkeypatch.setenv(
        "SALESFORCE_INSTANCE_URL",
        "https://hint.my.salesforce.com",
    )

    response = MagicMock()
    response.ok = True
    response.json.return_value = {"access_token": "tok-from-refresh"}
    mock_post.return_value = response

    token, instance_url = get_salesforce_access_token()
    assert token == "tok-from-refresh"
    assert instance_url == "https://hint.my.salesforce.com"


@patch("integrations.salesforce_client.requests.post")
def test_refresh_token_access_token_cached(
    mock_post: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated calls within cache TTL should not hit the token endpoint again."""
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", "client-id")
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("SALESFORCE_DOMAIN", "login.salesforce.com")
    monkeypatch.setenv("SALESFORCE_REFRESH_TOKEN", "refresh-abc")

    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "access_token": "tok-from-refresh",
        "instance_url": "https://example.my.salesforce.com",
    }
    mock_post.return_value = response

    first = get_salesforce_access_token()
    second = get_salesforce_access_token()
    assert first == second
    mock_post.assert_called_once()


@patch("integrations.salesforce_client.requests.post")
def test_auth_failure_raises_auth_error(
    mock_post: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed password auth should raise SalesforceAuthError with a clear message."""
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)

    response = MagicMock()
    response.ok = False
    response.json.return_value = {
        "error": "invalid_grant",
        "error_description": "authentication failure - IP restricted",
    }
    mock_post.return_value = response

    with pytest.raises(SalesforceAuthError, match="authentication failure"):
        get_salesforce_access_token()


@patch("integrations.salesforce_client.requests.get")
def test_fetch_approved_projects_maps_records(
    mock_get: MagicMock,
) -> None:
    """Successful SOQL response maps into ProjectApproval objects."""
    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "records": [
            _record(
                name="P-201",
                client="Brightline Corp",
                vendor="Acme Supplies",
                approved_date="2026-07-01",
                po_exists=True,
                amount=12500.0,
            ),
            _record(
                name="P-202",
                client="Horizon Labs",
                vendor="Delta Components",
                approved_date="2026-07-10",
                po_exists=False,
                amount=48250.5,
            ),
            _record(
                name="P-203",
                client="Summit Retail",
                vendor="Omega Parts Co",
                approved_date="2026-07-12",
                po_exists=False,
                amount=None,
            ),
        ]
    }
    mock_get.return_value = response

    results = fetch_approved_projects(
        access_token="tok",
        instance_url="https://example.my.salesforce.com",
    )

    assert len(results) == 3
    assert results[0].project_id == "P-201"
    assert results[0].client_name == "Brightline Corp"
    assert results[0].vendor_name == "Acme Supplies"
    assert results[0].po_exists is True
    assert results[0].estimated_amount == 12500.0
    assert results[0].approved_at == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert results[0].salesforce_id == "a00TEST000000001"

    assert results[1].project_id == "P-202"
    assert results[1].po_exists is False
    assert results[1].estimated_amount == 48250.5

    assert results[2].project_id == "P-203"
    assert results[2].po_exists is False
    assert results[2].estimated_amount == 0.0


@patch("integrations.salesforce_client.requests.get")
def test_po_exists_true_false_mapping(mock_get: MagicMock) -> None:
    """PO_Exists__c maps directly to the ProjectApproval.po_exists boolean."""
    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "records": [
            _record(
                name="P-T",
                client="Client A",
                vendor="Vendor A",
                approved_date="2026-07-01",
                po_exists=True,
                amount=1.0,
            ),
            _record(
                name="P-F",
                client="Client B",
                vendor="Vendor B",
                approved_date="2026-07-01",
                po_exists=False,
                amount=2.0,
            ),
        ]
    }
    mock_get.return_value = response

    results = fetch_approved_projects(
        access_token="tok",
        instance_url="https://example.my.salesforce.com",
    )
    by_id = {item.project_id: item for item in results}
    assert by_id["P-T"].po_exists is True
    assert by_id["P-F"].po_exists is False


@patch("integrations.salesforce_client.requests.get")
def test_malformed_record_raises_fetch_error(mock_get: MagicMock) -> None:
    """Records missing required fields should raise SalesforceFetchError."""
    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "records": [
            {
                "Name": "P-BAD",
                "Client_Name__c": "",
                "Vendor_Name__c": "Vendor",
                "Approved_Date__c": "2026-07-01",
                "PO_Exists__c": False,
                "Estimated_Amount__c": 10.0,
            }
        ]
    }
    mock_get.return_value = response

    with pytest.raises(SalesforceFetchError, match="Missing Client_Name__c"):
        fetch_approved_projects(
            access_token="tok",
            instance_url="https://example.my.salesforce.com",
        )


@patch("integrations.salesforce_client.requests.get")
def test_network_error_raises_fetch_error(mock_get: MagicMock) -> None:
    """Network failures during SOQL should be wrapped as SalesforceFetchError."""
    mock_get.side_effect = requests.Timeout("timed out")

    with pytest.raises(SalesforceFetchError, match="query request failed"):
        fetch_approved_projects(
            access_token="tok",
            instance_url="https://example.my.salesforce.com",
        )
