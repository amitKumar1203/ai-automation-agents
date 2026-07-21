"""Focused mocked tests for isolated Monday Intake routing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.services.monday_routing import MondayIntakeRoutingService
from integrations.monday_intake_client import (
    INTAKE_CATEGORIES,
    IntakeBoardConfig,
    MondayIntakeClient,
    MondayIntakeConfig,
    MondayIntakeConfigError,
    MondayIntakeItem,
)
from persistence import Database, EffectRepository


def _config(*, linked: bool = True) -> MondayIntakeConfig:
    boards = {
        category: IntakeBoardConfig(
            category=category,
            board_id=f"board-{category}",
            owner_id="42",
            external_submission_id_column_id="external_id",
            category_column_id="category",
            submitted_by_column_id="submitted_by",
            submission_text_column_id="text",
            owner_column_id="owner",
            previous_item_id_column_id="previous" if linked else None,
            replacement_item_id_column_id="replacement" if linked else None,
        )
        for category in INTAKE_CATEGORIES
    }
    return MondayIntakeConfig(api_token="token", boards=boards)


def _response(data: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"data": data}
    return response


def _effects(tmp_path: Path) -> EffectRepository:
    database = Database("", sqlite_path=tmp_path / "effects.db")
    database.migrate()
    return EffectRepository(database)


def _item(item_id: str, category: str) -> MondayIntakeItem:
    board_id = f"board-{category}"
    return MondayIntakeItem(
        item_id=item_id,
        board_id=board_id,
        category=category,
        name="Intake EXT-1",
        external_submission_id="EXT-1",
        url=f"https://monday.com/boards/{board_id}/pulses/{item_id}",
    )


def test_config_requires_all_intake_boards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MONDAY_API_TOKEN", "token")
    monkeypatch.setenv(
        "MONDAY_INTAKE_EXTERNAL_SUBMISSION_ID_COLUMN_ID", "external_id"
    )
    for category in INTAKE_CATEGORIES:
        monkeypatch.delenv(
            f"MONDAY_INTAKE_{category.upper()}_BOARD_ID", raising=False
        )
    with pytest.raises(
        MondayIntakeConfigError, match="MONDAY_INTAKE_NEW_PROJECT_BOARD_ID"
    ):
        MondayIntakeConfig.from_env()


def test_exact_lookup_paginates_every_board() -> None:
    session = MagicMock()
    responses = []
    for index, category in enumerate(INTAKE_CATEGORIES):
        first_items = [{
            "id": f"near-{index}",
            "name": "near",
            "column_values": [{"id": "external_id", "text": "EXT-10"}],
        }]
        cursor = "next-new" if category == "new_project" else None
        responses.append(
            _response({"boards": [{"items_page": {
                "cursor": cursor, "items": first_items
            }}]})
        )
        if cursor:
            responses.append(_response({"next_items_page": {
                "cursor": None,
                "items": [{
                    "id": "exact",
                    "name": "Intake EXT-1",
                    "column_values": [{"id": "external_id", "text": "EXT-1"}],
                }],
            }}))
    session.post.side_effect = responses
    client = MondayIntakeClient(_config(), session=session)

    matches = client.find_items_by_external_submission_id("EXT-1")

    assert [item.item_id for item in matches] == ["exact"]
    assert session.post.call_count == len(INTAKE_CATEGORIES) + 1
    assert all(call.kwargs["timeout"] == 10 for call in session.post.call_args_list)


def test_create_and_multi_column_update_encode_values() -> None:
    session = MagicMock()
    session.post.side_effect = [
        _response({"create_item": {"id": "item-1", "name": "Intake EXT-1"}}),
        _response({
            "change_multiple_column_values": {
                "id": "item-1", "name": "Intake EXT-1"
            }
        }),
    ]
    client = MondayIntakeClient(_config(), session=session)

    created = client.create_item(
        category="quote_request",
        external_submission_id="EXT-1",
        submitted_by="client@example.com",
        submission_text="Please quote this.",
    )
    updated = client.update_item(
        item_id=created.item_id,
        category="quote_request",
        external_submission_id="EXT-1",
        submitted_by="new@example.com",
        submission_text="Updated request.",
    )

    assert updated.item_id == "item-1"
    create_variables = session.post.call_args_list[0].kwargs["json"]["variables"]
    assert create_variables["itemName"] == "Intake EXT-1"
    assert json.loads(create_variables["columnValues"])["external_id"] == "EXT-1"
    update_variables = session.post.call_args_list[1].kwargs["json"]["variables"]
    assert json.loads(update_variables["columnValues"])["text"] == "Updated request."


def test_cross_board_recreates_links_and_archives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    client = MagicMock(spec=MondayIntakeClient)
    client.config = _config()
    old = _item("old-1", "general_inquiry")
    new = _item("new-1", "support_issue")
    client.find_items_by_external_submission_id.return_value = [old]
    client.create_item.return_value = new
    client.update_item.return_value = old
    client.archive_item.return_value = "old-1"
    client.board_url.return_value = "https://monday.com/boards/board-support_issue"

    result = MondayIntakeRoutingService(
        client=client, effects=_effects(tmp_path)
    ).route(
        external_submission_id="EXT-1",
        category="support_issue",
        submitted_by="client@example.com",
        submission_text="The installed sign is broken.",
    )

    assert result["action"] == "linked_existing"
    assert result["item"]["url"] == new.url
    assert result["board"]["url"].endswith("board-support_issue")
    client.create_item.assert_called_once_with(
        category="support_issue",
        external_submission_id="EXT-1",
        submitted_by="client@example.com",
        submission_text="The installed sign is broken.",
        previous_item_id="old-1",
    )
    assert client.update_item.call_args.kwargs["replacement_item_id"] == "new-1"
    client.archive_item.assert_called_once_with("old-1")


def test_dry_run_does_not_call_monday_or_claim_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "dry_run")
    client = MagicMock(spec=MondayIntakeClient)
    client.config = _config()
    effects = MagicMock(spec=EffectRepository)

    result = MondayIntakeRoutingService(client=client, effects=effects).route(
        external_submission_id="EXT-2",
        category="new_project",
        submitted_by="client@example.com",
        submission_text="A new storefront.",
    )

    assert result["status"] == "DRY_RUN"
    assert result["item_name"] == "Intake EXT-2"
    assert result["board"]["url"].endswith("board-new_project")
    assert "existing_records" in result
    assert not client.method_calls
    effects.begin.assert_not_called()


def test_live_effect_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    client = MagicMock(spec=MondayIntakeClient)
    client.config = _config()
    created = _item("new-1", "new_project")
    client.find_items_by_external_submission_id.return_value = []
    client.create_item.return_value = created
    client.board_url.return_value = "https://monday.com/boards/board-new_project"
    service = MondayIntakeRoutingService(client=client, effects=_effects(tmp_path))
    kwargs = {
        "external_submission_id": "EXT-1",
        "category": "new_project",
        "submitted_by": "client@example.com",
        "submission_text": "New project",
    }

    first = service.route(**kwargs)
    second = service.route(**kwargs)

    assert second == first
    client.create_item.assert_called_once()
    client.find_items_by_external_submission_id.assert_called_once()


def test_failed_live_effect_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    client = MagicMock(spec=MondayIntakeClient)
    client.config = _config()
    client.find_items_by_external_submission_id.side_effect = [
        TimeoutError("Monday timed out"),
        [],
    ]
    client.create_item.return_value = _item("new-1", "new_project")
    client.board_url.return_value = "https://monday.com/boards/board-new_project"
    effects = _effects(tmp_path)
    service = MondayIntakeRoutingService(client=client, effects=effects)
    kwargs = {
        "external_submission_id": "EXT-RETRY",
        "category": "new_project",
        "submitted_by": "client@example.com",
        "submission_text": "New project",
        "idempotency_key": "retry-key",
    }

    with pytest.raises(TimeoutError, match="timed out"):
        service.route(**kwargs)
    result = service.route(**kwargs)

    assert result["status"] == "SUCCESS"
    assert client.find_items_by_external_submission_id.call_count == 2
    replay = service.route(**kwargs)
    assert replay == result
    assert client.find_items_by_external_submission_id.call_count == 2


def test_in_progress_live_effect_cannot_false_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    client = MagicMock(spec=MondayIntakeClient)
    client.config = _config()
    effects = _effects(tmp_path)
    effects.begin(
        effect_type="monday_intake_routing",
        idempotency_key="active-key",
        request={"external_submission_id": "EXT-ACTIVE"},
    )

    with pytest.raises(RuntimeError, match="already in progress"):
        MondayIntakeRoutingService(client=client, effects=effects).route(
            external_submission_id="EXT-ACTIVE",
            category="new_project",
            submitted_by="client@example.com",
            submission_text="New project",
            idempotency_key="active-key",
        )

    client.find_items_by_external_submission_id.assert_not_called()
