"""Storefront Search agent — attach storefront imagery to project records."""

from __future__ import annotations

from agents.base_agent import BaseAgent
from integrations.storefront_search import search_storefront_image
from models.agent_result import AgentResult
from models.task import StorefrontProject

_LOW_CONFIDENCE_THRESHOLD = 0.75


class StorefrontSearchAgent(BaseAgent):
    """Find storefront imagery for a store address and recommend attachment."""

    def execute(self, task: StorefrontProject) -> AgentResult:
        address = str(task.store_address or "").strip()
        if task.existing_image_url.strip():
            return AgentResult(
                data={
                    "status": "ALREADY_ATTACHED",
                    "project_id": task.project_id,
                    "project_name": task.project_name,
                    "store_address": address,
                    "monday_item_id": task.monday_item_id,
                    "image_url": task.existing_image_url,
                },
                confidence=1.0,
                requires_approval=False,
                reasoning=(
                    f"Project '{task.project_name}' already has storefront imagery "
                    "on the Monday record — no search needed."
                ),
            )

        if not address:
            return AgentResult(
                data={
                    "status": "MISSING_ADDRESS",
                    "project_id": task.project_id,
                    "project_name": task.project_name,
                    "store_address": "",
                    "monday_item_id": task.monday_item_id,
                },
                confidence=1.0,
                requires_approval=False,
                reasoning=(
                    f"Project '{task.project_name}' has no store address — "
                    "add an address before running Storefront Search."
                ),
            )

        try:
            found = search_storefront_image(address)
        except Exception as exc:
            return AgentResult(
                data={
                    "status": "SEARCH_FAILED",
                    "project_id": task.project_id,
                    "project_name": task.project_name,
                    "store_address": address,
                    "monday_item_id": task.monday_item_id,
                    "error": str(exc)[:500],
                },
                confidence=1.0,
                requires_approval=True,
                reasoning=f"Storefront lookup failed for '{address}': {exc}",
            )

        if found is None or not found.image_url:
            return AgentResult(
                data={
                    "status": "NOT_FOUND",
                    "project_id": task.project_id,
                    "project_name": task.project_name,
                    "store_address": address,
                    "monday_item_id": task.monday_item_id,
                },
                confidence=0.9,
                requires_approval=False,
                reasoning=(
                    f"No storefront imagery found for '{address}'. "
                    "Ops can attach manually or retry with a fuller address."
                ),
            )

        status = (
            "LOW_CONFIDENCE"
            if found.confidence < _LOW_CONFIDENCE_THRESHOLD
            else "FOUND"
        )
        return AgentResult(
            data={
                "status": status,
                "project_id": task.project_id,
                "project_name": task.project_name,
                "store_address": address,
                "monday_item_id": task.monday_item_id,
                "image_url": found.image_url,
                "image_source": found.source,
                "place_name": found.place_name,
                "match_confidence": found.confidence,
            },
            confidence=found.confidence,
            requires_approval=status == "LOW_CONFIDENCE",
            reasoning=(
                f"Storefront candidate found for '{task.project_name}' at "
                f"'{address}' via {found.source} "
                f"(confidence {found.confidence:.0%})."
            ),
        )
