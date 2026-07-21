"""Locate storefront imagery for a store address (Phase 2 — no generative vision)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

import requests

REQUEST_TIMEOUT_SECONDS = 10


class StorefrontSearchError(RuntimeError):
    """Raised when an external storefront lookup fails."""


@dataclass(frozen=True)
class StorefrontSearchResult:
    image_url: str
    source: str
    confidence: float
    place_name: str = ""


def search_storefront_image(address: str) -> StorefrontSearchResult | None:
    """Return a candidate storefront image URL for ``address``, or None."""
    cleaned = str(address or "").strip()
    if not cleaned:
        return None

    api_key = (os.getenv("GOOGLE_PLACES_API_KEY") or "").strip()
    if api_key:
        try:
            return _search_google_places(cleaned, api_key)
        except StorefrontSearchError:
            raise
        except Exception as exc:
            raise StorefrontSearchError(f"Google Places lookup failed: {exc}") from exc

    return _mock_search(cleaned)


def _search_google_places(address: str, api_key: str) -> StorefrontSearchResult | None:
    response = requests.get(
        "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
        params={
            "input": address,
            "inputtype": "textquery",
            "fields": "name,photos,formatted_address",
            "key": api_key,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    status = str(payload.get("status") or "")
    if status not in {"OK", "ZERO_RESULTS"}:
        raise StorefrontSearchError(
            f"Google Places returned status {status}: {payload.get('error_message')}"
        )
    candidates = payload.get("candidates") or []
    if not candidates:
        return None

    best = candidates[0]
    photos = best.get("photos") or []
    if not photos:
        return StorefrontSearchResult(
            image_url="",
            source="google_places_no_photo",
            confidence=0.45,
            place_name=str(best.get("name") or address),
        )

    photo_ref = str(photos[0].get("photo_reference") or "").strip()
    if not photo_ref:
        return None
    image_url = (
        "https://maps.googleapis.com/maps/api/place/photo"
        f"?maxwidth=1200&photo_reference={photo_ref}&key={api_key}"
    )
    return StorefrontSearchResult(
        image_url=image_url,
        source="google_places",
        confidence=0.88,
        place_name=str(best.get("name") or address),
    )


def _mock_search(address: str) -> StorefrontSearchResult | None:
    """Deterministic demo lookup when no Places API key is configured."""
    lowered = address.lower()
    if any(token in lowered for token in ("unknown", "missing", "nowhere")):
        return None

    digest = hashlib.sha256(lowered.encode()).hexdigest()[:12]
    # Stable placeholder image for demos/UAT (no external API required).
    image_url = f"https://picsum.photos/seed/storefront-{digest}/800/600"
    confidence = 0.82 if len(lowered) > 12 else 0.62
    return StorefrontSearchResult(
        image_url=image_url,
        source="mock_storefront_catalog",
        confidence=confidence,
        place_name=address.split(",")[0].strip() or address,
    )


def result_to_dict(result: StorefrontSearchResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "image_url": result.image_url,
        "source": result.source,
        "confidence": result.confidence,
        "place_name": result.place_name,
    }
