"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from supervisor import audit_log


@pytest.fixture(autouse=True)
def _isolated_audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a fresh temp SQLite file for every test (avoids polluted prod DB).

    Plain ``:memory:`` cannot be used with connection-per-operation because
    each connection gets a separate empty database.
    """
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.delenv("WRITE_BACK_MODE", raising=False)

    db_path = tmp_path / "test_audit_log.db"
    audit_log.configure_database(str(db_path))
    from backend.services.kpi_cache import init_kpi_table

    init_kpi_table()
    yield
    audit_log.clear_audit_log()
