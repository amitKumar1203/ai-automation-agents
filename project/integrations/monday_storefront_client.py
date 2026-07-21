"""Monday.com reader for Storefront Search projects."""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from integrations.monday_client import MondayConfigError, MondayFetchError, _post_graphql
from models.task import StorefrontProject

COLUMN_PROJECT_ID = "Project ID"
COLUMN_STORE_ADDRESS = "Store Address"
COLUMN_STOREFRONT_IMAGE = "Storefront Image"

_REQUIRED_STOREFRONT_COLUMNS = (
    COLUMN_PROJECT_ID,
    COLUMN_STORE_ADDRESS,
    COLUMN_STOREFRONT_IMAGE,
)

_BOARD_QUERY = """
query ($boardId: [ID!], $limit: Int!) {
  boards(ids: $boardId) {
    columns { id title }
    items_page(limit: $limit) {
      items {
        id
        name
        column_values { id text value }
      }
    }
  }
}
"""


def get_storefront_board_id() -> str:
    board_id = (os.getenv("MONDAY_STOREFRONT_BOARD_ID") or "").strip()
    if not board_id:
        raise MondayConfigError(
            "Missing MONDAY_STOREFRONT_BOARD_ID. Set it in project/.env for Storefront Search."
        )
    return board_id


def fetch_storefront_projects() -> list[StorefrontProject]:
    """Load projects needing storefront imagery from Monday.com."""
    board_id = get_storefront_board_id()
    try:
        data = _post_graphql(
            _BOARD_QUERY,
            {"boardId": [board_id], "limit": 500},
        )
        boards = data.get("boards") or []
        if not boards:
            raise MondayFetchError(
                f"Monday.com storefront board {board_id!r} was not found."
            )
        board = boards[0]
        title_to_id = _storefront_column_map(board.get("columns") or [])
        items = (board.get("items_page") or {}).get("items") or []
        projects: list[StorefrontProject] = []
        for item in items:
            projects.append(_item_to_project(item, title_to_id, board_id))
        return projects
    except (MondayConfigError, MondayFetchError):
        raise
    except Exception as exc:
        raise MondayFetchError(
            f"Monday storefront board fetch failed: {exc}"
        ) from exc


def update_storefront_image_column(
    *,
    item_id: str,
    image_url: str,
    column_title: str = COLUMN_STOREFRONT_IMAGE,
) -> dict[str, Any]:
    """Write a link/image URL to the storefront image column."""
    board_id = get_storefront_board_id()
    data = _post_graphql(
        """
        query ($boardId: [ID!]) {
          boards(ids: $boardId) { columns { id title } }
        }
        """,
        {"boardId": [board_id]},
    )
    boards = data.get("boards") or []
    if not boards:
        raise MondayFetchError(f"Monday storefront board {board_id!r} not found.")
    title_to_id = _storefront_column_map(boards[0].get("columns") or [])
    if column_title not in title_to_id:
        raise MondayFetchError(
            f"Column {column_title!r} not found on storefront board {board_id}."
        )
    column_id = title_to_id[column_title]
    value = json.dumps({"url": image_url, "text": "Storefront image"})
    changed = _post_graphql(
        """
        mutation ($boardId: ID!, $itemId: ID!, $columnId: String!, $value: JSON!) {
          change_column_value(
            board_id: $boardId,
            item_id: $itemId,
            column_id: $columnId,
            value: $value
          ) { id }
        }
        """,
        {
            "boardId": board_id,
            "itemId": item_id,
            "columnId": column_id,
            "value": value,
        },
    )
    return {
        "item_id": item_id,
        "column_id": column_id,
        "column_title": column_title,
        "changed_id": (changed.get("change_column_value") or {}).get("id"),
        "image_url": image_url,
    }


def _storefront_column_map(columns: list[dict[str, Any]]) -> dict[str, str]:
    """Map column title -> column id for the Storefront Projects board."""
    title_to_id = {
        str(column.get("title", "")).strip(): str(column.get("id", ""))
        for column in columns
        if column.get("id")
    }
    missing = [
        title for title in _REQUIRED_STOREFRONT_COLUMNS if title not in title_to_id
    ]
    if missing:
        raise MondayFetchError(
            "Monday.com storefront board is missing required columns: "
            + ", ".join(missing)
            + ". Expected titles: "
            + ", ".join(_REQUIRED_STOREFRONT_COLUMNS)
            + "."
        )
    return title_to_id


def _item_to_project(
    item: dict[str, Any],
    title_to_id: dict[str, str],
    board_id: str,
) -> StorefrontProject:
    values = item.get("column_values") or []
    project_id = _column_text(values, title_to_id.get(COLUMN_PROJECT_ID, ""))
    address = _column_text(values, title_to_id.get(COLUMN_STORE_ADDRESS, ""))
    image_url = _column_text(values, title_to_id.get(COLUMN_STOREFRONT_IMAGE, ""))
    item_id = str(item.get("id") or "").strip()
    name = str(item.get("name") or project_id or item_id)
    if not project_id:
        project_id = item_id or name
    return StorefrontProject(
        project_id=project_id,
        project_name=name,
        store_address=address,
        monday_item_id=item_id or None,
        existing_image_url=image_url,
    )


def _column_text(values: list[dict[str, Any]], column_id: str) -> str:
    if not column_id:
        return ""
    for value in values:
        if str(value.get("id") or "") == column_id:
            return str(value.get("text") or "").strip()
    return ""
