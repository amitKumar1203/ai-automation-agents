"""Tests for the read-only Gmail client (mocked API — no live network calls)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from integrations.gmail_client import (
    GmailFetchError,
    _apply_thread_filters,
    _build_thread_filter_context,
    _oauth_client_config,
    classify_sender,
    fetch_recent_threads,
    html_to_plain_text,
)
from models.task import EmailMessage, EmailThread


def test_html_to_plain_text_converts_br_tags() -> None:
    """HTML line breaks from Gmail bodies should become newlines."""
    assert (
        html_to_plain_text("Hello Team<br> <br> Build Number- 166<br>Thanks")
        == "Hello Team\n\nBuild Number- 166\nThanks"
    )


def test_oauth_client_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.env` / env vars should be preferred for Desktop OAuth client config."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret-value")
    monkeypatch.setenv("GOOGLE_PROJECT_ID", "demo-project")

    config = _oauth_client_config()
    assert config["installed"]["client_id"] == "id.apps.googleusercontent.com"
    assert config["installed"]["client_secret"] == "secret-value"
    assert config["installed"]["project_id"] == "demo-project"


def test_oauth_client_config_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear error when neither .env nor credentials.json is available."""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        "integrations.gmail_client.CREDENTIALS_PATH",
        MagicMock(exists=MagicMock(return_value=False)),
    )
    with pytest.raises(GmailFetchError, match="Missing Gmail OAuth credentials"):
        _oauth_client_config()


def _b64(text: str) -> str:
    import base64

    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8").rstrip("=")


def test_classify_sender_team_internal_client() -> None:
    """Sender classification uses exact email for team and domain for internal."""
    own = "amit@softude.com"
    assert classify_sender("Amit Kumar <amit@softude.com>", own) == "team"
    assert classify_sender("Asif Ansari <asif@softude.com>", own) == "internal"
    assert classify_sender("asif@softude.com", own) == "internal"
    assert classify_sender("Client User <client@acme.com>", own) == "client"
    assert classify_sender("client@acme.com", own) == "client"


def test_fetch_recent_threads_maps_messages() -> None:
    """fetch_recent_threads should convert Gmail payloads into EmailThread objects."""
    service = MagicMock()
    service.users().getProfile().execute.return_value = {
        "emailAddress": "amit@softude.com",
    }
    service.users().threads().list().execute.return_value = {
        "threads": [{"id": "thread-abc"}]
    }
    service.users().threads().get().execute.return_value = {
        "id": "thread-abc",
        "snippet": "fallback snippet",
        "messages": [
            {
                "id": "msg-1",
                "internalDate": "1720500000000",  # epoch ms
                "snippet": "from client",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {"name": "From", "value": "Client User <client@acme.com>"},
                    ],
                    "body": {"data": _b64("Hello from client")},
                },
            },
            {
                "id": "msg-2",
                "internalDate": "1720501800000",
                "snippet": "from internal colleague",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {
                            "name": "From",
                            "value": "Asif Ansari <asif@softude.com>",
                        },
                    ],
                    "body": {"data": _b64("Internal note")},
                },
            },
            {
                "id": "msg-3",
                "internalDate": "1720503600000",
                "snippet": "from team",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {"name": "From", "value": "Amit Kumar <amit@softude.com>"},
                    ],
                    "body": {"data": _b64("Reply from team")},
                },
            },
        ],
    }

    threads = fetch_recent_threads(service, max_results=5)

    assert len(threads) == 1
    thread = threads[0]
    assert thread.thread_id == "thread-abc"
    assert len(thread.messages) == 3
    assert thread.messages[0].sender == "client"
    assert thread.messages[0].text == "Hello from client"
    assert thread.messages[0].sender_email == "client@acme.com"
    assert thread.messages[0].timestamp == datetime.fromtimestamp(
        1720500000000 / 1000, tz=timezone.utc
    )
    assert thread.messages[1].sender == "internal"
    assert thread.messages[1].text == "Internal note"
    assert thread.messages[2].sender == "team"
    assert thread.messages[2].text == "Reply from team"


def test_fetch_recent_threads_uses_snippet_fallback() -> None:
    """When body text is unavailable, snippet should be used as message text."""
    service = MagicMock()
    service.users().getProfile().execute.return_value = {
        "emailAddress": "team@example.com",
    }
    service.users().threads().list().execute.return_value = {
        "threads": [{"id": "thread-xyz"}]
    }
    service.users().threads().get().execute.return_value = {
        "id": "thread-xyz",
        "snippet": "thread-level snippet",
        "messages": [
            {
                "id": "msg-1",
                "internalDate": "1720500000000",
                "snippet": "message snippet only",
                "payload": {
                    "mimeType": "multipart/alternative",
                    "headers": [
                        {"name": "From", "value": "someone@outside.com"},
                    ],
                    "parts": [],
                    "body": {},
                },
            }
        ],
    }

    threads = fetch_recent_threads(service)
    assert threads[0].messages[0].text == "message snippet only"
    assert threads[0].messages[0].sender == "client"


def _thread_detail(
    *,
    thread_id: str,
    subject: str,
    from_email: str,
    body: str,
    internal_date: str = "1720500000000",
) -> dict:
    return {
        "id": thread_id,
        "snippet": body,
        "messages": [
            {
                "id": f"msg-{thread_id}",
                "internalDate": internal_date,
                "snippet": body,
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {"name": "From", "value": from_email},
                        {"name": "Subject", "value": subject},
                    ],
                    "body": {"data": _b64(body)},
                },
            }
        ],
    }


def _mock_service_for_threads(thread_details: list[dict]) -> MagicMock:
    service = MagicMock()
    service.users().getProfile().execute.return_value = {
        "emailAddress": "amit@softude.com",
    }
    service.users().threads().list().execute.return_value = {
        "threads": [{"id": detail["id"]} for detail in thread_details]
    }

    def _get_thread(*_args: object, **_kwargs: object) -> MagicMock:
        getter = MagicMock()
        thread_id = _kwargs.get("id")
        detail = next(item for item in thread_details if item["id"] == thread_id)
        getter.execute.return_value = detail
        return getter

    service.users().threads().get.side_effect = _get_thread
    return service


def test_fetch_recent_threads_without_filters_returns_all() -> None:
    """No filters should preserve existing fetch behavior."""
    service = _mock_service_for_threads(
        [
            _thread_detail(
                thread_id="thread-1",
                subject="Hello",
                from_email="Client User <client@acme.com>",
                body="General update",
            ),
            _thread_detail(
                thread_id="thread-2",
                subject="Order status",
                from_email="Nirmal Kumar <nirmal@gmail.com>",
                body="Where is my order?",
            ),
        ]
    )

    threads = fetch_recent_threads(service, max_results=5)

    assert [thread.thread_id for thread in threads] == ["thread-1", "thread-2"]


def test_fetch_recent_threads_sender_filter_case_insensitive() -> None:
    """sender_filter should match the last message sender email substring."""
    service = _mock_service_for_threads(
        [
            _thread_detail(
                thread_id="thread-1",
                subject="Hello",
                from_email="Client User <client@acme.com>",
                body="General update",
            ),
            _thread_detail(
                thread_id="thread-2",
                subject="Order status",
                from_email="Nirmal Kumar <nirmal@gmail.com>",
                body="Where is my order?",
            ),
        ]
    )

    threads = fetch_recent_threads(service, sender_filter="NIRMAL")

    assert len(threads) == 1
    assert threads[0].thread_id == "thread-2"


def test_fetch_recent_threads_keyword_filter_matches_subject_or_body() -> None:
    """keyword_filter should match subject or message text case-insensitively."""
    service = _mock_service_for_threads(
        [
            _thread_detail(
                thread_id="thread-1",
                subject="Weekly update",
                from_email="Client User <client@acme.com>",
                body="All good here",
            ),
            _thread_detail(
                thread_id="thread-2",
                subject="Order status",
                from_email="Nirmal Kumar <nirmal@gmail.com>",
                body="Where is my order?",
            ),
        ]
    )

    threads = fetch_recent_threads(service, keyword_filter="order status")

    assert len(threads) == 1
    assert threads[0].thread_id == "thread-2"


def test_fetch_recent_threads_both_filters_use_and_logic() -> None:
    """When both filters are set, a thread must match both to be included."""
    service = _mock_service_for_threads(
        [
            _thread_detail(
                thread_id="thread-1",
                subject="Order status",
                from_email="Client User <client@acme.com>",
                body="Need an update",
            ),
            _thread_detail(
                thread_id="thread-2",
                subject="Order status",
                from_email="Nirmal Kumar <nirmal@gmail.com>",
                body="Where is my order?",
            ),
        ]
    )

    threads = fetch_recent_threads(
        service,
        sender_filter="nirmal",
        keyword_filter="order status",
    )

    assert len(threads) == 1
    assert threads[0].thread_id == "thread-2"


def test_fetch_recent_threads_filters_can_return_empty_list() -> None:
    """Filters that match nothing should return an empty list without errors."""
    service = _mock_service_for_threads(
        [
            _thread_detail(
                thread_id="thread-1",
                subject="Hello",
                from_email="Client User <client@acme.com>",
                body="General update",
            )
        ]
    )

    threads = fetch_recent_threads(
        service,
        sender_filter="does-not-exist",
        keyword_filter="missing keyword",
    )

    assert threads == []


def test_apply_thread_filters_ignores_blank_filter_values() -> None:
    """Whitespace-only filters should behave like no filter."""
    thread = EmailThread(
        thread_id="thread-1",
        messages=[
            EmailMessage(
                sender="client",
                timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
                text="Hello",
            )
        ],
    )
    context = _build_thread_filter_context(
        [
            {
                "internalDate": "1720500000000",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "client@acme.com"},
                        {"name": "Subject", "value": "Hello"},
                    ]
                },
            }
        ],
        thread.messages,
    )

    filtered = _apply_thread_filters(
        [thread],
        [context],
        sender_filter="   ",
        keyword_filter="",
    )

    assert filtered == [thread]
