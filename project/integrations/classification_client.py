"""Claude integration for structured client-inquiry classification."""

from __future__ import annotations

from typing import Any

from integrations.vision_verification import (
    VisionConfigError,
    get_anthropic_client as get_shared_anthropic_client,
)

_CLASSIFICATION_MODEL = "claude-sonnet-4-5"
_CLASSIFICATION_TIMEOUT_SECONDS = 10.0
_TOOL_NAME = "report_intake_classification"
_ALLOWED_CATEGORIES = frozenset(
    {"new_project", "quote_request", "support_issue", "general_inquiry"}
)


class ClassificationConfigError(Exception):
    """Raised when the Anthropic client cannot be configured."""


class ClassificationError(Exception):
    """Raised when classification fails or Claude returns invalid output."""


def get_anthropic_client() -> Any:
    """Return the shared Anthropic client configured with a 10-second timeout.

    The shared initializer loads ``ANTHROPIC_API_KEY`` through the project's
    existing dotenv setup. Configuration failures are translated into the
    classification-specific exception exposed by this module.
    """
    try:
        client = get_shared_anthropic_client()
        return client.with_options(timeout=_CLASSIFICATION_TIMEOUT_SECONDS)
    except VisionConfigError as exc:
        raise ClassificationConfigError(
            "ANTHROPIC_API_KEY is not set. Add it to project/.env to use "
            "intake classification."
        ) from exc
    except Exception as exc:
        raise ClassificationConfigError(
            f"Could not initialize the Anthropic classification client: {exc}"
        ) from exc


def _classification_tool() -> dict[str, Any]:
    """Return the forced tool schema for reliable intake categorization."""
    return {
        "name": _TOOL_NAME,
        "description": (
            "Classify one client inquiry into exactly one intake category. "
            "Use conservative confidence: lower the score when wording is "
            "ambiguous or plausibly belongs to multiple categories."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": sorted(_ALLOWED_CATEGORIES),
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation for the selected category.",
                },
            },
            "required": ["category", "confidence", "reasoning"],
            "additionalProperties": False,
        },
    }


def _system_prompt() -> str:
    """Define categories and examples for consistent classification."""
    return (
        "You classify freeform client inquiries for an operations workflow.\n"
        "Choose exactly one category:\n"
        "- new_project: the client wants to start a new installation or order, "
        "often with specifications or a timeline. Examples: 'I need a new lobby "
        "sign installed next month'; 'We want to order graphics for three stores.'\n"
        "- quote_request: the primary intent is pricing or a cost estimate. "
        "Examples: 'How much would this installation cost?'; 'Please send a quote.'\n"
        "- support_issue: something about existing work is wrong, broken, delayed, "
        "or the client is complaining. Examples: 'The installed panel is peeling'; "
        "'Our delivery is late and we need help.'\n"
        "- general_inquiry: company, hours, capabilities, or other general questions "
        "that do not fit above. Examples: 'What areas do you serve?'; "
        "'Are you open on Saturdays?'\n"
        "Be conservative with confidence. If multiple categories are plausible, "
        "still choose the best one but use a lower confidence score instead of "
        "pretending the intent is certain."
    )


def _extract_tool_result(response: Any) -> dict[str, Any]:
    """Extract the classification tool payload from a Claude response."""
    for block in getattr(response, "content", []) or []:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == _TOOL_NAME
        ):
            tool_input = getattr(block, "input", None)
            if isinstance(tool_input, dict):
                return tool_input
    raise ClassificationError(
        "Claude did not return a structured intake classification."
    )


def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize Claude's structured classification payload."""
    category = str(raw.get("category") or "").strip().lower()
    if category not in _ALLOWED_CATEGORIES:
        raise ClassificationError(
            f"Unexpected intake category '{raw.get('category')}'."
        )

    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise ClassificationError(
            "Classification confidence must be a number."
        ) from exc
    if not 0.0 <= confidence <= 1.0:
        raise ClassificationError(
            "Classification confidence must be between 0.0 and 1.0."
        )

    reasoning = str(raw.get("reasoning") or "").strip()
    if not reasoning:
        raise ClassificationError("Classification reasoning was empty.")

    return {
        "category": category,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def classify_intake_text(text: str) -> dict[str, Any]:
    """Classify freeform inquiry text with Claude structured tool use.

    Raises:
        ClassificationConfigError: If Anthropic credentials are unavailable.
        ClassificationError: On timeout, rate limit, API, or response failures.
    """
    normalized_text = (text or "").strip()
    if not normalized_text:
        raise ClassificationError("Intake text cannot be empty.")

    client = get_anthropic_client()
    try:
        response = client.messages.create(
            model=_CLASSIFICATION_MODEL,
            max_tokens=512,
            system=_system_prompt(),
            tools=[_classification_tool()],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Classify this client inquiry and call the required tool:\n\n"
                        f"{normalized_text}"
                    ),
                }
            ],
        )
        return _normalize_result(_extract_tool_result(response))
    except ClassificationError:
        raise
    except Exception as exc:
        raise ClassificationError(
            f"Claude intake classification failed: {exc}"
        ) from exc
