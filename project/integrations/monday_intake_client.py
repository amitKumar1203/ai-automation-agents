"""Isolated Monday.com client for classified Intake routing."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

import requests

MONDAY_API_URL = "https://api.monday.com/v2"
REQUEST_TIMEOUT_SECONDS = 10
PAGE_SIZE = 100
INTAKE_CATEGORIES = (
    "new_project",
    "quote_request",
    "support_issue",
    "general_inquiry",
    "unclassified",
)


class MondayIntakeConfigError(ValueError):
    """Raised when the Intake-specific Monday configuration is invalid."""


class MondayIntakeError(RuntimeError):
    """Raised for Monday transport, GraphQL, or response errors."""


@dataclass(frozen=True)
class IntakeBoardConfig:
    category: str
    board_id: str
    owner_id: str | None
    external_submission_id_column_id: str
    category_column_id: str | None = None
    submitted_by_column_id: str | None = None
    submission_text_column_id: str | None = None
    owner_column_id: str | None = None
    previous_item_id_column_id: str | None = None
    replacement_item_id_column_id: str | None = None


@dataclass(frozen=True)
class MondayIntakeConfig:
    api_token: str
    boards: Mapping[str, IntakeBoardConfig]
    api_url: str = MONDAY_API_URL
    web_base_url: str = "https://monday.com"

    @classmethod
    def from_env(cls) -> "MondayIntakeConfig":
        token = _required_env("MONDAY_API_TOKEN")
        shared = {
            field: _env(f"MONDAY_INTAKE_{env_name}_COLUMN_ID")
            for field, env_name in _COLUMN_ENV_NAMES.items()
        }

        boards: dict[str, IntakeBoardConfig] = {}
        for category in INTAKE_CATEGORIES:
            prefix = f"MONDAY_INTAKE_{category.upper()}"
            values = {
                field: _env(f"{prefix}_{env_name}_COLUMN_ID") or shared[field]
                for field, env_name in _COLUMN_ENV_NAMES.items()
            }
            if not values["external_submission_id_column_id"]:
                raise MondayIntakeConfigError(
                    "Missing "
                    f"{prefix}_EXTERNAL_SUBMISSION_ID_COLUMN_ID or shared "
                    "MONDAY_INTAKE_EXTERNAL_SUBMISSION_ID_COLUMN_ID."
                )
            boards[category] = IntakeBoardConfig(
                category=category,
                board_id=_required_env(f"{prefix}_BOARD_ID"),
                owner_id=_env(f"{prefix}_OWNER_ID"),
                **values,
            )
        board_ids = [board.board_id for board in boards.values()]
        if len(set(board_ids)) != len(board_ids):
            raise MondayIntakeConfigError(
                "Monday Intake categories must use separate, unique board IDs."
            )

        return cls(
            api_token=token,
            boards=boards,
            api_url=_env("MONDAY_INTAKE_API_URL") or MONDAY_API_URL,
            web_base_url=(
                _env("MONDAY_INTAKE_WEB_BASE_URL") or "https://monday.com"
            ).rstrip("/"),
        )

    def board_for(self, category: str) -> IntakeBoardConfig:
        normalized = str(category).strip().lower()
        try:
            return self.boards[normalized]
        except KeyError as exc:
            raise MondayIntakeConfigError(
                f"Unsupported Intake category {category!r}; expected one of "
                f"{', '.join(INTAKE_CATEGORIES)}."
            ) from exc


_COLUMN_ENV_NAMES = {
    "external_submission_id_column_id": "EXTERNAL_SUBMISSION_ID",
    "category_column_id": "CATEGORY",
    "submitted_by_column_id": "SUBMITTED_BY",
    "submission_text_column_id": "SUBMISSION_TEXT",
    "owner_column_id": "OWNER",
    "previous_item_id_column_id": "PREVIOUS_ITEM_ID",
    "replacement_item_id_column_id": "REPLACEMENT_ITEM_ID",
}


@dataclass(frozen=True)
class MondayIntakeItem:
    item_id: str
    board_id: str
    category: str
    name: str
    external_submission_id: str
    url: str


def _env(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


def _required_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise MondayIntakeConfigError(f"Missing {name}.")
    return value


def stable_item_name(external_submission_id: str) -> str:
    """Build a deterministic name that never depends on mutable intake fields."""
    external_id = str(external_submission_id).strip()
    if not external_id:
        raise ValueError("external_submission_id is required")
    return f"Intake {external_id}"


class MondayIntakeClient:
    """Small GraphQL client scoped only to classified Intake boards."""

    def __init__(
        self,
        config: MondayIntakeConfig | None = None,
        *,
        session: Any = requests,
    ) -> None:
        self.config = config or MondayIntakeConfig.from_env()
        self._session = session

    def _post(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._session.post(
                self.config.api_url,
                json={"query": query, "variables": variables},
                headers={
                    "Authorization": self.config.api_token,
                    "Content-Type": "application/json",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise MondayIntakeError(f"Monday Intake request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise MondayIntakeError(
                "Monday Intake API returned a non-JSON response."
            ) from exc
        errors = payload.get("errors")
        if errors:
            messages = "; ".join(
                str(error.get("message", error)) for error in errors
            )
            raise MondayIntakeError(f"Monday Intake GraphQL error: {messages}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MondayIntakeError("Monday Intake response is missing data.")
        return data

    def item_url(self, board_id: str, item_id: str) -> str:
        return f"{self.config.web_base_url}/boards/{board_id}/pulses/{item_id}"

    def board_url(self, board_id: str) -> str:
        return f"{self.config.web_base_url}/boards/{board_id}"

    def find_items_by_external_submission_id(
        self, external_submission_id: str
    ) -> list[MondayIntakeItem]:
        """Find exact matches across every Intake board and every result page."""
        needle = str(external_submission_id).strip()
        if not needle:
            raise ValueError("external_submission_id is required")
        matches: list[MondayIntakeItem] = []
        for category in INTAKE_CATEGORIES:
            board = self.config.board_for(category)
            cursor: str | None = None
            while True:
                page = self._fetch_page(board.board_id, cursor)
                for item in page.get("items") or []:
                    external_id = _column_text(
                        item.get("column_values") or [],
                        board.external_submission_id_column_id,
                    )
                    if external_id == needle:
                        item_id = str(item.get("id") or "").strip()
                        if not item_id:
                            raise MondayIntakeError(
                                f"Monday item on board {board.board_id} has no id."
                            )
                        matches.append(
                            MondayIntakeItem(
                                item_id=item_id,
                                board_id=board.board_id,
                                category=category,
                                name=str(item.get("name") or ""),
                                external_submission_id=external_id,
                                url=self.item_url(board.board_id, item_id),
                            )
                        )
                cursor = str(page.get("cursor") or "").strip() or None
                if not cursor:
                    break
        return matches

    def find_items_by_submitted_by(
        self,
        submitted_by: str,
        *,
        target_category: str | None = None,
    ) -> list[MondayIntakeItem]:
        """Find items whose submitted-by column matches the contact email."""
        needle = str(submitted_by).strip().lower()
        if not needle:
            raise ValueError("submitted_by is required")
        matches: list[MondayIntakeItem] = []
        categories = (
            (target_category,)
            if target_category
            else INTAKE_CATEGORIES
        )
        for category in categories:
            board = self.config.board_for(category)
            if not board.submitted_by_column_id:
                continue
            cursor: str | None = None
            while True:
                page = self._fetch_page(board.board_id, cursor)
                for item in page.get("items") or []:
                    contact = _column_text(
                        item.get("column_values") or [],
                        board.submitted_by_column_id,
                    ).lower()
                    if needle not in contact and contact not in needle:
                        continue
                    item_id = str(item.get("id") or "").strip()
                    if not item_id:
                        continue
                    external_id = _column_text(
                        item.get("column_values") or [],
                        board.external_submission_id_column_id,
                    )
                    matches.append(
                        MondayIntakeItem(
                            item_id=item_id,
                            board_id=board.board_id,
                            category=category,
                            name=str(item.get("name") or ""),
                            external_submission_id=external_id,
                            url=self.item_url(board.board_id, item_id),
                        )
                    )
                cursor = str(page.get("cursor") or "").strip() or None
                if not cursor:
                    break
        return matches

    def _fetch_page(self, board_id: str, cursor: str | None) -> dict[str, Any]:
        if cursor:
            data = self._post(
                """
                query ($cursor: String!, $limit: Int!) {
                  next_items_page(cursor: $cursor, limit: $limit) {
                    cursor
                    items { id name column_values { id text value } }
                  }
                }
                """,
                {"cursor": cursor, "limit": PAGE_SIZE},
            )
            page = data.get("next_items_page")
        else:
            data = self._post(
                """
                query ($boardId: [ID!], $limit: Int!) {
                  boards(ids: $boardId) {
                    items_page(limit: $limit) {
                      cursor
                      items { id name column_values { id text value } }
                    }
                  }
                }
                """,
                {"boardId": [board_id], "limit": PAGE_SIZE},
            )
            boards = data.get("boards") or []
            if not boards:
                raise MondayIntakeError(
                    f"Monday Intake board {board_id!r} was not found."
                )
            page = boards[0].get("items_page")
        if not isinstance(page, dict) or not isinstance(page.get("items", []), list):
            raise MondayIntakeError("Monday Intake items page is malformed.")
        return page

    def intake_column_values(
        self,
        *,
        category: str,
        external_submission_id: str,
        submitted_by: str,
        submission_text: str,
        previous_item_id: str | None = None,
    ) -> dict[str, Any]:
        board = self.config.board_for(category)
        values: dict[str, Any] = {
            board.external_submission_id_column_id: external_submission_id,
        }
        _put(values, board.category_column_id, category)
        _put(values, board.submitted_by_column_id, submitted_by)
        _put(values, board.submission_text_column_id, submission_text)
        if board.owner_id and board.owner_column_id:
            values[board.owner_column_id] = {"personsAndTeams": [
                {"id": int(board.owner_id) if board.owner_id.isdigit() else board.owner_id,
                 "kind": "person"}
            ]}
        _put(values, board.previous_item_id_column_id, previous_item_id)
        return values

    def create_item(
        self,
        *,
        category: str,
        external_submission_id: str,
        submitted_by: str,
        submission_text: str,
        previous_item_id: str | None = None,
    ) -> MondayIntakeItem:
        board = self.config.board_for(category)
        name = stable_item_name(external_submission_id)
        data = self._post(
            """
            mutation ($boardId: ID!, $itemName: String!, $columnValues: JSON!) {
              create_item(
                board_id: $boardId,
                item_name: $itemName,
                column_values: $columnValues
              ) { id name }
            }
            """,
            {
                "boardId": board.board_id,
                "itemName": name,
                "columnValues": json.dumps(
                    self.intake_column_values(
                        category=category,
                        external_submission_id=external_submission_id,
                        submitted_by=submitted_by,
                        submission_text=submission_text,
                        previous_item_id=previous_item_id,
                    )
                ),
            },
        )
        created = data.get("create_item") or {}
        item_id = str(created.get("id") or "").strip()
        if not item_id:
            raise MondayIntakeError("Monday create_item response is missing item id.")
        return MondayIntakeItem(
            item_id=item_id,
            board_id=board.board_id,
            category=category,
            name=str(created.get("name") or name),
            external_submission_id=external_submission_id,
            url=self.item_url(board.board_id, item_id),
        )

    def update_item(
        self,
        *,
        item_id: str,
        category: str,
        external_submission_id: str,
        submitted_by: str,
        submission_text: str,
        replacement_item_id: str | None = None,
    ) -> MondayIntakeItem:
        board = self.config.board_for(category)
        values = self.intake_column_values(
            category=category,
            external_submission_id=external_submission_id,
            submitted_by=submitted_by,
            submission_text=submission_text,
        )
        _put(values, board.replacement_item_id_column_id, replacement_item_id)
        data = self._post(
            """
            mutation (
              $boardId: ID!, $itemId: ID!, $columnValues: JSON!
            ) {
              change_multiple_column_values(
                board_id: $boardId,
                item_id: $itemId,
                column_values: $columnValues
              ) { id name }
            }
            """,
            {
                "boardId": board.board_id,
                "itemId": item_id,
                "columnValues": json.dumps(values),
            },
        )
        changed = data.get("change_multiple_column_values") or {}
        changed_id = str(changed.get("id") or "").strip()
        if not changed_id:
            raise MondayIntakeError(
                "Monday change_multiple_column_values response is missing item id."
            )
        return MondayIntakeItem(
            item_id=changed_id,
            board_id=board.board_id,
            category=category,
            name=str(changed.get("name") or stable_item_name(external_submission_id)),
            external_submission_id=external_submission_id,
            url=self.item_url(board.board_id, changed_id),
        )

    def archive_item(self, item_id: str) -> str:
        data = self._post(
            "mutation ($itemId: ID!) { archive_item(item_id: $itemId) { id } }",
            {"itemId": item_id},
        )
        archived_id = str((data.get("archive_item") or {}).get("id") or "").strip()
        if not archived_id:
            raise MondayIntakeError("Monday archive_item response is missing item id.")
        return archived_id


def _column_text(values: list[dict[str, Any]], column_id: str) -> str:
    for value in values:
        if str(value.get("id") or "") == column_id:
            return str(value.get("text") or "").strip()
    return ""


def _put(values: dict[str, Any], column_id: str | None, value: Any) -> None:
    if column_id and value is not None:
        values[column_id] = value
