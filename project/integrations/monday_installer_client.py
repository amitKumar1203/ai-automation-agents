"""Monday.com reader/writer for Installer Matching boards."""

from __future__ import annotations

import json
import os
from typing import Any

from integrations.monday_client import MondayConfigError, MondayFetchError, _post_graphql
from models.task import InstallProject, InstallerProfile

COLUMN_PROJECT_ID = "Project ID"
COLUMN_INSTALL_REGION = "Install Region"
COLUMN_ASSIGNED_INSTALLER = "Assigned Installer"
COLUMN_INSTALL_DATE = "Install Date"

COLUMN_REGION = "Region"
COLUMN_CAPACITY = "Capacity"
COLUMN_ACTIVE_JOBS = "Active Jobs"
COLUMN_EMAIL = "Email"

_REQUIRED_PROJECT_COLUMNS = (
    COLUMN_PROJECT_ID,
    COLUMN_INSTALL_REGION,
    COLUMN_ASSIGNED_INSTALLER,
)
_REQUIRED_INSTALLER_COLUMNS = (
    COLUMN_REGION,
    COLUMN_CAPACITY,
    COLUMN_ACTIVE_JOBS,
    COLUMN_EMAIL,
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


def get_install_projects_board_id() -> str:
    board_id = (os.getenv("MONDAY_INSTALL_PROJECTS_BOARD_ID") or "").strip()
    if not board_id:
        raise MondayConfigError(
            "Missing MONDAY_INSTALL_PROJECTS_BOARD_ID. "
            "Set it in project/.env for Installer Matching."
        )
    return board_id


def get_installers_board_id() -> str:
    board_id = (os.getenv("MONDAY_INSTALLERS_BOARD_ID") or "").strip()
    if not board_id:
        raise MondayConfigError(
            "Missing MONDAY_INSTALLERS_BOARD_ID. "
            "Set it in project/.env for Installer Matching."
        )
    return board_id


def fetch_install_projects() -> list[InstallProject]:
    board_id = get_install_projects_board_id()
    board = _fetch_board(board_id, "install projects")
    title_to_id = _column_map_for(
        board.get("columns") or [],
        _REQUIRED_PROJECT_COLUMNS,
        board_label="install projects",
    )
    items = (board.get("items_page") or {}).get("items") or []
    projects: list[InstallProject] = []
    for item in items:
        values = item.get("column_values") or []
        project_id = _column_text(values, title_to_id.get(COLUMN_PROJECT_ID, ""))
        item_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or project_id or item_id)
        if not project_id:
            project_id = item_id or name
        projects.append(
            InstallProject(
                project_id=project_id,
                project_name=name,
                install_region=_column_text(
                    values, title_to_id.get(COLUMN_INSTALL_REGION, "")
                ),
                assigned_installer=_column_text(
                    values, title_to_id.get(COLUMN_ASSIGNED_INSTALLER, "")
                ),
                install_date=_column_text(
                    values,
                    title_to_id.get(COLUMN_INSTALL_DATE, ""),
                ),
                monday_item_id=item_id or None,
            )
        )
    return projects


def fetch_installer_roster() -> list[InstallerProfile]:
    board_id = get_installers_board_id()
    board = _fetch_board(board_id, "installers")
    title_to_id = _column_map_for(
        board.get("columns") or [],
        _REQUIRED_INSTALLER_COLUMNS,
        board_label="installers",
    )
    items = (board.get("items_page") or {}).get("items") or []
    roster: list[InstallerProfile] = []
    for item in items:
        values = item.get("column_values") or []
        item_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or item_id)
        installer_id = item_id or name
        roster.append(
            InstallerProfile(
                installer_id=installer_id,
                name=name,
                region=_column_text(values, title_to_id.get(COLUMN_REGION, "")),
                capacity=_column_number(values, title_to_id.get(COLUMN_CAPACITY, "")),
                active_jobs=_column_number(
                    values, title_to_id.get(COLUMN_ACTIVE_JOBS, "")
                ),
                email=_column_text(values, title_to_id.get(COLUMN_EMAIL, "")),
                monday_item_id=item_id or None,
            )
        )
    return roster


def update_assigned_installer_column(
    *,
    item_id: str,
    installer_name: str,
    column_title: str = COLUMN_ASSIGNED_INSTALLER,
) -> dict[str, Any]:
    board_id = get_install_projects_board_id()
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
        raise MondayFetchError(f"Monday install projects board {board_id!r} not found.")
    title_to_id = _column_map_for(
        boards[0].get("columns") or [],
        _REQUIRED_PROJECT_COLUMNS,
        board_label="install projects",
    )
    if column_title not in title_to_id:
        raise MondayFetchError(
            f"Column {column_title!r} not found on install projects board {board_id}."
        )
    column_id = title_to_id[column_title]
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
            "value": json.dumps(installer_name),
        },
    )
    return {
        "item_id": item_id,
        "column_id": column_id,
        "column_title": column_title,
        "changed_id": (changed.get("change_column_value") or {}).get("id"),
        "installer_name": installer_name,
    }


def _fetch_board(board_id: str, label: str) -> dict[str, Any]:
    try:
        data = _post_graphql(
            _BOARD_QUERY,
            {"boardId": [board_id], "limit": 500},
        )
        boards = data.get("boards") or []
        if not boards:
            raise MondayFetchError(f"Monday.com {label} board {board_id!r} was not found.")
        return boards[0]
    except (MondayConfigError, MondayFetchError):
        raise
    except Exception as exc:
        raise MondayFetchError(f"Monday {label} board fetch failed: {exc}") from exc


def _column_map_for(
    columns: list[dict[str, Any]],
    required_titles: tuple[str, ...],
    *,
    board_label: str,
) -> dict[str, str]:
    title_to_id = {
        str(column.get("title", "")).strip(): str(column.get("id", ""))
        for column in columns
        if column.get("id")
    }
    missing = [title for title in required_titles if title not in title_to_id]
    if missing:
        raise MondayFetchError(
            f"Monday.com {board_label} board is missing required columns: "
            + ", ".join(missing)
            + ". Expected titles: "
            + ", ".join(required_titles)
            + "."
        )
    return title_to_id


def _column_text(values: list[dict[str, Any]], column_id: str) -> str:
    if not column_id:
        return ""
    for value in values:
        if str(value.get("id") or "") == column_id:
            return str(value.get("text") or "").strip()
    return ""


def _column_number(values: list[dict[str, Any]], column_id: str) -> int:
    if not column_id:
        return 0
    for value in values:
        if str(value.get("id") or "") == column_id:
            text = str(value.get("text") or "").strip()
            if text.isdigit():
                return int(text)
            raw = str(value.get("value") or "").strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, (int, float)):
                        return int(parsed)
                except json.JSONDecodeError:
                    pass
    return 0
