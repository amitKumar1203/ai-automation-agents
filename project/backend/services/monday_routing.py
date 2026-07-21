"""Idempotent routing of classified Intake submissions to Monday.com."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.services.intake_existing_records import (
    enrich_routing_with_existing_records,
    pick_existing_item_for_update,
)
from integrations.monday_intake_client import (
    INTAKE_CATEGORIES,
    MondayIntakeClient,
    MondayIntakeItem,
    stable_item_name,
)
from persistence import Database, EffectRepository
from supervisor.write_back import get_write_back_mode, intake_check_existing_records_enabled

EFFECT_TYPE = "monday_intake_routing"


class MondayIntakeRoutingService:
    def __init__(
        self,
        *,
        client: MondayIntakeClient | None = None,
        effects: EffectRepository | None = None,
    ) -> None:
        self.client = client
        if effects is None:
            database = Database.from_audit_log()
            database.migrate()
            effects = EffectRepository(database)
        self.effects = effects

    def route(
        self,
        *,
        external_submission_id: str,
        category: str,
        submitted_by: str,
        submission_text: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        external_id = str(external_submission_id).strip()
        normalized_category = str(category).strip().lower()
        if not external_id:
            raise ValueError("external_submission_id is required")
        if normalized_category not in INTAKE_CATEGORIES:
            raise ValueError(
                f"category must be one of {', '.join(INTAKE_CATEGORIES)}"
            )
        request = {
            "external_submission_id": external_id,
            "category": normalized_category,
            "submitted_by": str(submitted_by).strip(),
            "submission_text": str(submission_text),
            "item_name": stable_item_name(external_id),
        }
        mode = get_write_back_mode()
        default_key = (
            f"{external_id}:"
            + hashlib.sha256(
                json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        key = (idempotency_key or default_key).strip()
        if not key:
            raise ValueError("idempotency_key is required")

        if mode != "live":
            client = self.client or MondayIntakeClient()
            board = client.config.board_for(normalized_category)
            return {
                "status": "DRY_RUN",
                "mode": mode,
                "action": "upsert",
                "idempotency_key": key,
                "external_submission_id": external_id,
                "category": normalized_category,
                "item_name": request["item_name"],
                "existing_records": {
                    "enabled": intake_check_existing_records_enabled(),
                    "dry_run": True,
                },
                "board": {
                    "id": board.board_id,
                    "category": normalized_category,
                    "url": (
                        f"{client.config.web_base_url.rstrip('/')}"
                        f"/boards/{board.board_id}"
                    ),
                },
                "item": None,
                "previous_items": [],
                "archived_items": [],
                "planned": request,
            }

        effect, created = self.effects.begin(
            effect_type=EFFECT_TYPE,
            idempotency_key=key,
            request=request,
        )
        if not created:
            if effect["status"] == "completed" and isinstance(
                effect.get("result"), dict
            ):
                return effect["result"]
            # A concurrent worker still owns this external effect. Treating that
            # as a routing result would incorrectly complete the submission even
            # though no Monday write has been observed.
            raise RuntimeError("Monday Intake routing is already in progress")

        try:
            result = self._route_live(request=request, idempotency_key=key)
        except Exception as exc:
            self.effects.complete(effect["id"], error=str(exc))
            raise
        self.effects.complete(effect["id"], result=result)
        return result

    def _route_live(
        self, *, request: dict[str, str], idempotency_key: str
    ) -> dict[str, Any]:
        client = self.client or MondayIntakeClient()
        category = request["category"]
        external_id = request["external_submission_id"]
        matches = client.find_items_by_external_submission_id(external_id)
        existing = enrich_routing_with_existing_records(
            client,
            submitted_by=request["submitted_by"],
            target_category=category,
            external_matches=matches,
        )
        desired_board = client.config.board_for(category)
        desired = [
            item for item in matches if item.board_id == desired_board.board_id
        ]
        if not desired:
            linked = pick_existing_item_for_update(
                existing,
                external_matches=matches,
                target_category=category,
            )
            if linked is not None:
                desired = [linked]
        previous = [
            item for item in matches if item.board_id != desired_board.board_id
        ]
        if existing.get("match_count"):
            for summary in existing.get("other_boards") or []:
                item_id = str(summary.get("id") or "")
                if item_id and not any(item.item_id == item_id for item in previous):
                    previous.append(
                        MondayIntakeItem(
                            item_id=item_id,
                            board_id=str(summary.get("board_id") or ""),
                            category=str(summary.get("category") or ""),
                            name=str(summary.get("name") or ""),
                            external_submission_id=str(
                                summary.get("external_submission_id") or ""
                            ),
                            url=str(summary.get("url") or ""),
                        )
                    )

        if desired:
            current = desired[0]
            routed = client.update_item(
                item_id=current.item_id,
                category=category,
                external_submission_id=external_id,
                submitted_by=request["submitted_by"],
                submission_text=request["submission_text"],
            )
            action = "updated"
            # Any duplicate on the destination board is stale too.
            previous.extend(desired[1:])
        else:
            previous_id = previous[0].item_id if previous else None
            routed = client.create_item(
                category=category,
                external_submission_id=external_id,
                submitted_by=request["submitted_by"],
                submission_text=request["submission_text"],
                previous_item_id=previous_id,
            )
            if existing.get("match_count"):
                action = "linked_existing" if previous_id else "created"
            else:
                action = "recreated" if previous else "created"

        archived: list[dict[str, Any]] = []
        for old in previous:
            old_board = client.config.board_for(old.category)
            linked = bool(old_board.replacement_item_id_column_id)
            if linked:
                client.update_item(
                    item_id=old.item_id,
                    category=old.category,
                    external_submission_id=external_id,
                    submitted_by=request["submitted_by"],
                    submission_text=request["submission_text"],
                    replacement_item_id=routed.item_id,
                )
            client.archive_item(old.item_id)
            archived.append({**_item_result(old), "linked_to_item_id": (
                routed.item_id if linked else None
            )})

        return {
            "status": "SUCCESS",
            "mode": "live",
            "action": action,
            "idempotency_key": idempotency_key,
            "external_submission_id": external_id,
            "category": category,
            "item_name": request["item_name"],
            "existing_records": existing,
            "board": {
                "id": desired_board.board_id,
                "category": category,
                "url": client.board_url(desired_board.board_id),
            },
            "item": _item_result(routed),
            "previous_items": [_item_result(item) for item in previous],
            "archived_items": archived,
        }


def _item_result(item: MondayIntakeItem) -> dict[str, str]:
    return {
        "id": item.item_id,
        "board_id": item.board_id,
        "category": item.category,
        "name": item.name,
        "url": item.url,
    }


def route_intake_to_monday(
    *,
    external_submission_id: str,
    category: str,
    submitted_by: str,
    submission_text: str,
    idempotency_key: str | None = None,
    client: MondayIntakeClient | None = None,
    effects: EffectRepository | None = None,
) -> dict[str, Any]:
    """Convenience entrypoint; workers/routes intentionally do not call it yet."""
    return MondayIntakeRoutingService(client=client, effects=effects).route(
        external_submission_id=external_submission_id,
        category=category,
        submitted_by=submitted_by,
        submission_text=submission_text,
        idempotency_key=idempotency_key,
    )
