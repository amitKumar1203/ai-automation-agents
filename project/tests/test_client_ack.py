"""Tests for template client auto-ack (no AI)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.services.client_ack import (
    already_acked,
    mark_acked,
    send_client_acks,
)


@pytest.fixture()
def ack_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "ack.db"
    monkeypatch.setattr(
        "backend.services.client_ack._DEFAULT_DB_PATH",
        db,
    )
    return db


def test_client_ack_dry_run(ack_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WRITE_BACK_MODE", raising=False)
    monkeypatch.setenv("CLIENT_AUTO_ACK_ENABLED", "true")
    send = MagicMock()
    outcome = send_client_acks(
        [
            {
                "thread_id": "T1",
                "client_email": "client@acme.com",
                "subject": "Order status",
                "hours_pending": 30,
            }
        ],
        send_email=send,
    )
    assert outcome["execution_status"] == "DRY_RUN"
    send.assert_not_called()
    assert already_acked("T1") is False


def test_client_ack_live_sends_once(ack_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    monkeypatch.setenv("CLIENT_AUTO_ACK_ENABLED", "true")
    send = MagicMock(return_value={"id": "msg-1", "threadId": "T1"})
    row = {
        "thread_id": "T1",
        "client_email": "client@acme.com",
        "subject": "Help",
    }
    first = send_client_acks([row], send_email=send)
    assert first["execution_status"] == "SUCCESS"
    send.assert_called_once()
    assert send.call_args.kwargs["to"] == "client@acme.com"
    assert send.call_args.kwargs["thread_id"] == "T1"
    assert "automated acknowledgment" in send.call_args.kwargs["body_text"].lower()
    assert already_acked("T1") is True

    send.reset_mock()
    second = send_client_acks([row], send_email=send)
    assert second["execution_status"] == "SKIPPED"
    send.assert_not_called()


def test_client_ack_skips_without_email(
    ack_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    send = MagicMock()
    outcome = send_client_acks(
        [{"thread_id": "T2", "client_email": "", "subject": "x"}],
        send_email=send,
    )
    assert outcome["results"][0]["execution_status"] == "SKIPPED"
    send.assert_not_called()


def test_client_ack_disabled(ack_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLIENT_AUTO_ACK_ENABLED", "false")
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    send = MagicMock()
    outcome = send_client_acks(
        [{"thread_id": "T3", "client_email": "a@b.com", "subject": "x"}],
        send_email=send,
    )
    assert outcome["execution_status"] == "SKIPPED"
    send.assert_not_called()


def test_mark_acked_roundtrip(ack_db: Path) -> None:
    mark_acked("TX", client_email="c@x.com", message_id="m1")
    assert already_acked("TX") is True


def test_email_batch_defers_client_ack_for_hitl(
    ack_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WRITE_BACK_MODE", raising=False)
    monkeypatch.setenv("CLIENT_AUTO_ACK_ENABLED", "true")
    monkeypatch.delenv("NOTIFY_OWNER_EMAIL", raising=False)

    from backend.services.agent_runs import run_email_batch

    summary = run_email_batch(use_real_gmail=False, notify_owner=False)
    assert summary["unanswered_count"] >= 1
    assert "client_ack" in summary
    assert summary["client_ack"]["execution_status"] == "DEFERRED"
    assert "audit approve" in summary["client_ack"]["execution_detail"].lower()
