"""Tests for Monday installer board write-back."""

import json
from unittest.mock import patch

from integrations.monday_installer_client import update_assigned_installer_column


def test_update_assigned_installer_uses_text_column_shape() -> None:
    """Monday text columns require {"text": "..."} in change_column_value."""
    captured: dict = {}

    def fake_post_graphql(query: str, variables: dict) -> dict:
        if "change_column_value" in query:
            captured["variables"] = variables
            return {"change_column_value": {"id": variables["itemId"]}}
        return {
            "boards": [
                {
                    "columns": [
                        {"id": "text_col", "title": "Project ID"},
                        {"id": "text_region", "title": "Install Region"},
                        {"id": "text_installer", "title": "Assigned Installer"},
                    ]
                }
            ]
        }

    with patch(
        "integrations.monday_installer_client._post_graphql",
        side_effect=fake_post_graphql,
    ), patch(
        "integrations.monday_installer_client.get_install_projects_board_id",
        return_value="5030067898",
    ):
        result = update_assigned_installer_column(
            item_id="2794274976",
            installer_name="Chicago Field Team",
        )

    assert result["installer_name"] == "Chicago Field Team"
    assert captured["variables"]["value"] == json.dumps(
        {"text": "Chicago Field Team"}
    )
