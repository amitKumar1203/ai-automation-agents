"""Tests for Gmail account profile endpoint (header avatar)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app


def test_gmail_profile_endpoint(monkeypatch) -> None:
    monkeypatch.delenv("API_KEY", raising=False)
    with patch(
        "backend.routes.email_agent.get_account_profile",
        return_value={
            "email": "amit@softude.com",
            "name": "Amit Kumar",
            "picture": "https://lh3.googleusercontent.com/a/photo",
            "picture_source": "google",
        },
    ):
        client = TestClient(app)
        response = client.get("/api/email-agent/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "amit@softude.com"
    assert body["picture_source"] == "google"
    assert "googleusercontent" in body["picture"]
