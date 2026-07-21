"""Clean extracted plain-text email bodies for dashboard display.

Strips quoted reply chains, signatures, disclaimers, and HTML conversion
artifacts so only the new message content remains.
"""

from __future__ import annotations

import re

_MIN_CLEAN_LENGTH = 3
_FALLBACK_CHARS = 200

# Truncate at the earliest match start (reply chains).
_QUOTE_PATTERNS: tuple[str, ...] = (
    r"(?im)^On .+?\bwrote:\s*$",
    r"(?im)^-{3,}\s*Original Message\s*-{3,}\s*$",
    r"(?im)^From:\s*.+?\r?\nSent:\s*.+?\r?\nTo:\s*.+?\r?\nSubject:",
    r"(?im)^>.*$",
)

# Standalone closing lines that typically start a signature block.
_SIGNATURE_PATTERNS: tuple[str, ...] = (
    r"(?im)^Best\s+Regards,?\s*$",
    r"(?im)^Thanks\s*(?:&|and)\s*Regards,?\s*$",
    r"(?im)^Regards,?\s*$",
    r"(?im)^Thanks,\s*$",
    r"(?im)^Sincerely,?\s*$",
)

# Legal / confidentiality blocks.
_DISCLAIMER_PATTERNS: tuple[str, ...] = (
    r"(?im)^DISCLAIMER:",
    r"(?im)^This email and any files transmitted",
    r"(?im)^CONFIDENTIAL\b",
    r"(?i)intended for the recipient",
)

_IMAGE_PLACEHOLDER_RE = re.compile(r"\[image:[^\]]*\]", re.IGNORECASE)


def _earliest_match_start(text: str, patterns: tuple[str, ...]) -> int | None:
    """Return the smallest start index among all pattern matches, if any."""
    earliest: int | None = None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match is None:
            continue
        start = match.start()
        if earliest is None or start < earliest:
            earliest = start
    return earliest


def _truncate_at_earliest_marker(text: str) -> str:
    """Keep only text before the first quote, signature, or disclaimer marker."""
    cut_at = _earliest_match_start(
        text,
        _QUOTE_PATTERNS + _SIGNATURE_PATTERNS + _DISCLAIMER_PATTERNS,
    )
    if cut_at is not None:
        return text[:cut_at]
    return text


def _collapse_blank_lines(text: str) -> str:
    """Collapse runs of blank lines into a single blank line."""
    lines = text.splitlines()
    collapsed: list[str] = []
    previous_blank = False

    for line in lines:
        is_blank = not line.strip()
        if is_blank:
            if not previous_blank:
                collapsed.append("")
            previous_blank = True
            continue
        collapsed.append(line.rstrip())
        previous_blank = False

    return "\n".join(collapsed)


def normalize_email_body(text: str) -> str:
    """Normalize HTML-email / marketing-mail plain-text into Gmail-like readable body.

    HTML newsletters often become space-padded, center-aligned blobs after tag
    stripping. This collapses intra-line whitespace, trims lines, drops
    decorative separators, and limits blank lines — without using AI.
    """
    if not text:
        return ""

    # Common HTML leftovers that survive tag stripping.
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)

    cleaned_lines: list[str] = []
    previous_blank = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue
        # Skip pure decorative separators from HTML templates.
        if re.fullmatch(r"[-_=.*·•\s]{3,}", line):
            continue
        cleaned_lines.append(line)
        previous_blank = False

    return "\n".join(cleaned_lines).strip()


def clean_email_text(raw_text: str) -> str:
    """Return readable message body text without quotes, signatures, or disclaimers.

    Processing order:
    1. Remove ``[image: ...]`` placeholders from HTML-to-text conversion
    2. Truncate at the earliest reply chain, signature closing, or disclaimer marker
    3. Normalize whitespace (HTML layout artifacts → Gmail-like plain text)
    4. If the result is empty or shorter than 3 characters, fall back to the
       first 200 characters of the original ``raw_text`` (also normalized)

    Args:
        raw_text: Plain-text body or snippet extracted from a Gmail message.

    Returns:
        Cleaned message text suitable for dashboard display.
    """
    if not raw_text:
        return ""

    original = raw_text
    text = _IMAGE_PLACEHOLDER_RE.sub("", original)
    text = _truncate_at_earliest_marker(text)
    text = normalize_email_body(text)

    if len(text) < _MIN_CLEAN_LENGTH:
        fallback = normalize_email_body(original)
        if len(fallback) > _FALLBACK_CHARS:
            return fallback[:_FALLBACK_CHARS].rstrip()
        return fallback

    return text
