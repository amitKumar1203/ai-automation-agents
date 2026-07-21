"""Detect returning clients on Intake Monday boards before creating items."""

from __future__ import annotations

import re
from typing import Any

from integrations.monday_intake_client import MondayIntakeClient, MondayIntakeItem
from supervisor.write_back import intake_check_existing_records_enabled


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def normalize_contact(value: str) -> str:
    """Extract a lowercased email from a name/email field."""
    text = str(value or "").strip().lower()
    match = _EMAIL_RE.search(text)
    return match.group(0) if match else text


def find_existing_intake_records(
    client: MondayIntakeClient,
    submitted_by: str,
    *,
    target_category: str,
) -> list[MondayIntakeItem]:
    """Return Monday Intake items whose submitted-by column matches the contact."""
    needle = normalize_contact(submitted_by)
    if not needle or "@" not in needle:
        return []
    return client.find_items_by_submitted_by(needle, target_category=target_category)


def enrich_routing_with_existing_records(
    client: MondayIntakeClient,
    *,
    submitted_by: str,
    target_category: str,
    external_matches: list[MondayIntakeItem],
) -> dict[str, Any]:
    """Summarize prior Intake items for the same contact (doc: checks existing records)."""
    if not intake_check_existing_records_enabled():
        return {"enabled": False, "matches": []}

    by_contact = find_existing_intake_records(
        client,
        submitted_by,
        target_category=target_category,
    )
    unique: dict[str, MondayIntakeItem] = {item.item_id: item for item in by_contact}
    for item in external_matches:
        unique[item.item_id] = item
    matches = list(unique.values())
    same_board = [
        item for item in matches if item.category == target_category
    ]
    other_boards = [
        item for item in matches if item.category != target_category
    ]
    return {
        "enabled": True,
        "contact": normalize_contact(submitted_by),
        "match_count": len(matches),
        "same_board": [_item_summary(item) for item in same_board],
        "other_boards": [_item_summary(item) for item in other_boards],
        "matches": [_item_summary(item) for item in matches],
    }


def pick_existing_item_for_update(
    existing: dict[str, Any],
    *,
    external_matches: list[MondayIntakeItem],
    target_category: str,
) -> MondayIntakeItem | None:
    """Prefer external-id match, else same-board contact match for upsert."""
    desired = [
        item for item in external_matches if item.category == target_category
    ]
    if desired:
        return desired[0]
    if not existing.get("enabled"):
        return None
    same_board = existing.get("same_board") or []
    if not same_board:
        return None
    first = same_board[0]
    return MondayIntakeItem(
        item_id=str(first["id"]),
        board_id=str(first["board_id"]),
        category=str(first["category"]),
        name=str(first.get("name") or ""),
        external_submission_id=str(first.get("external_submission_id") or ""),
        url=str(first.get("url") or ""),
    )


def _item_summary(item: MondayIntakeItem) -> dict[str, str]:
    return {
        "id": item.item_id,
        "board_id": item.board_id,
        "category": item.category,
        "name": item.name,
        "external_submission_id": item.external_submission_id,
        "url": item.url,
    }
