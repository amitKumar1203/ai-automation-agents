"""Deployment contract tests for the production Intake worker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.routes import cron

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_production_cors_requires_exact_configured_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "https://dashboard.example.com/, https://ops.example.com",
    )
    assert main._allowed_cors_origins() == [
        "https://dashboard.example.com",
        "https://ops.example.com",
    ]

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="cannot contain"):
        main._allowed_cors_origins()


def test_vercel_retains_daily_poll_and_runs_intake_every_minute() -> None:
    config = json.loads((PROJECT_ROOT / "vercel.json").read_text())
    crons = {entry["path"]: entry["schedule"] for entry in config["crons"]}
    assert crons["/api/cron/poll-all"] == "0 6 * * *"
    assert crons["/api/cron/intake"] == "* * * * *"


def test_intake_cron_requires_secret_and_drains_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRON_SECRET", "cron-secret")
    monkeypatch.setattr(
        cron,
        "drain_intake_jobs",
        lambda limit: {
            "worker_id": "worker-test",
            "limit": limit,
            "claimed": 1,
            "succeeded": 1,
            "retried": 0,
            "dead": 0,
        },
    )
    client = TestClient(main.app)

    assert client.get("/api/cron/intake").status_code == 401
    response = client.get(
        "/api/cron/intake?limit=7",
        headers={"Authorization": "Bearer cron-secret"},
    )
    assert response.status_code == 200
    assert response.json()["intake"]["limit"] == 7


def test_start_script_targets_backend_entrypoint() -> None:
    script = (PROJECT_ROOT / "start.sh").read_text()
    assert "backend.main:app" in script
    assert "api.main:app" not in script
