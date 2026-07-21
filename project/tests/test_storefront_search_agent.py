"""Tests for Storefront Search agent."""

from agents.storefront_search_agent import StorefrontSearchAgent
from models.task import StorefrontProject


def test_storefront_already_attached() -> None:
    agent = StorefrontSearchAgent()
    result = agent.execute(
        StorefrontProject(
            project_id="P1",
            project_name="Demo",
            store_address="123 Main",
            existing_image_url="https://example.com/img.jpg",
        )
    )
    assert result.data["status"] == "ALREADY_ATTACHED"
    assert result.requires_approval is False


def test_storefront_missing_address() -> None:
    agent = StorefrontSearchAgent()
    result = agent.execute(
        StorefrontProject(
            project_id="P2",
            project_name="Empty",
            store_address="",
        )
    )
    assert result.data["status"] == "MISSING_ADDRESS"


def test_storefront_mock_found(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    agent = StorefrontSearchAgent()
    result = agent.execute(
        StorefrontProject(
            project_id="P3",
            project_name="Riverwalk",
            store_address="1200 Main St, Austin, TX",
            monday_item_id="mon-1",
        )
    )
    assert result.data["status"] in {"FOUND", "LOW_CONFIDENCE"}
    assert result.data["image_url"]
    assert result.data["monday_item_id"] == "mon-1"


def test_storefront_not_found_address(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    agent = StorefrontSearchAgent()
    result = agent.execute(
        StorefrontProject(
            project_id="P4",
            project_name="Missing",
            store_address="unknown location nowhere",
        )
    )
    assert result.data["status"] == "NOT_FOUND"
