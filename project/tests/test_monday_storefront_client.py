"""Tests for Monday storefront board column validation."""

import pytest

from integrations.monday_client import MondayFetchError
from integrations.monday_storefront_client import _storefront_column_map


def test_storefront_column_map_ok() -> None:
    columns = [
        {"id": "col_pid", "title": "Project ID"},
        {"id": "col_addr", "title": "Store Address"},
        {"id": "col_img", "title": "Storefront Image"},
    ]
    mapping = _storefront_column_map(columns)
    assert mapping["Project ID"] == "col_pid"
    assert mapping["Store Address"] == "col_addr"
    assert mapping["Storefront Image"] == "col_img"


def test_storefront_column_map_rejects_vendor_columns() -> None:
    columns = [
        {"id": "col_pid", "title": "Project ID"},
        {"id": "col_budget", "title": "Budget"},
        {"id": "col_notes", "title": "Notes"},
    ]
    with pytest.raises(MondayFetchError, match="storefront board is missing required columns"):
        _storefront_column_map(columns)
