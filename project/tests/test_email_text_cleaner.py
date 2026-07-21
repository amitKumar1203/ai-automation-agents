"""Tests for integrations.email_text_cleaner."""

from integrations.email_text_cleaner import clean_email_text

REALISTIC_SAMPLE = (
    "Hi Amit, As I discussed with you, I am in internal discussion with HR "
    "and team so please allow me some time I will get back to you on the same.\n"
    "Best Regards,\n"
    "[image: great place work]\n"
    "Asif Ansari\n"
    "Technical Project Manager\n"
    "Softude Infotech Pvt Ltd\n"
    "Phone: +91 1234567890\n"
    "DISCLAIMER: The content of this email is confidential and intended "
    "for the recipient only."
)

EXPECTED_REALISTIC = (
    "Hi Amit, As I discussed with you, I am in internal discussion with HR "
    "and team so please allow me some time I will get back to you on the same."
)


def test_strips_signature_block_and_disclaimer() -> None:
    """Signature closings and legal disclaimers should be removed."""
    raw = (
        "Hello team,\n"
        "Please review the attached document.\n"
        "Best Regards,\n"
        "Jane Doe\n"
        "Project Manager\n"
        "DISCLAIMER: The content of this email is confidential."
    )
    assert clean_email_text(raw) == "Hello team,\nPlease review the attached document."


def test_strips_gmail_quoted_reply() -> None:
    """Gmail-style 'On ... wrote:' blocks and quoted lines should be removed."""
    raw = (
        "Sounds good, I will follow up tomorrow.\n"
        "\n"
        "On Wed, Jul 15, 2026 at 10:30 AM, Client User <client@acme.com> wrote:\n"
        "> Any update on my order?\n"
        "> Thanks."
    )
    assert clean_email_text(raw) == "Sounds good, I will follow up tomorrow."


def test_strips_image_placeholders() -> None:
    """Embedded image placeholders from HTML conversion should be removed."""
    raw = (
        "Hi there,\n"
        "[image: company logo]\n"
        "Please see the update below.\n"
        "[image: footer badge]"
    )
    assert clean_email_text(raw) == "Hi there,\n\nPlease see the update below."


def test_strips_outlook_original_message() -> None:
    """Outlook forwarded headers should remove everything after the marker."""
    raw = (
        "Forwarding for visibility.\n"
        "\n"
        "-----Original Message-----\n"
        "From: sender@example.com\n"
        "Sent: Monday, July 15, 2026 9:00 AM\n"
        "To: team@example.com\n"
        "Subject: RE: Status"
    )
    assert clean_email_text(raw) == "Forwarding for visibility."


def test_plain_short_message_mostly_unchanged() -> None:
    """Messages without markers should only be trimmed."""
    raw = "  Quick question about delivery.  \n\n"
    assert clean_email_text(raw) == "Quick question about delivery."


def test_fallback_when_stripping_leaves_nothing() -> None:
    """Over-aggressive input should fall back to truncated original text."""
    raw = "DISCLAIMER: confidential only."
    result = clean_email_text(raw)
    assert result
    assert result == raw.strip()
    assert len(result) >= 3


def test_realistic_softude_style_message() -> None:
    """Realistic internal email with signature, image, and disclaimer."""
    assert clean_email_text(REALISTIC_SAMPLE) == EXPECTED_REALISTIC


def test_preserves_thanks_mid_sentence() -> None:
    """Inline 'Thanks,' in normal prose should not trigger signature cut."""
    raw = "Thanks, I will send the report by end of day."
    assert clean_email_text(raw) == raw


def test_normalizes_html_newsletter_whitespace() -> None:
    """Space-padded / centered HTML email layouts should read like Gmail plain text."""
    from integrations.email_text_cleaner import normalize_email_body

    raw = (
        "Softude\n"
        "                    Time Log Reminder\n"
        "                              Time log entry for 16/07/2026 is overdue.\n"
        "\n"
        "\n"
        "Please submit your time log.\n"
        "          Add Time Log\n"
        "----------\n"
        "Want to opt out of email notifications? Update your preferences."
    )
    assert normalize_email_body(raw) == (
        "Softude\n"
        "Time Log Reminder\n"
        "Time log entry for 16/07/2026 is overdue.\n"
        "\n"
        "Please submit your time log.\n"
        "Add Time Log\n"
        "Want to opt out of email notifications? Update your preferences."
    )
