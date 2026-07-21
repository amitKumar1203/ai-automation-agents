"""Tests for Intake existing-record detection."""

from backend.services.intake_existing_records import normalize_contact


def test_normalize_contact_extracts_email() -> None:
    assert normalize_contact("Rahul Client <rahul@client.com>") == "rahul@client.com"
    assert normalize_contact("RAHUL@CLIENT.COM") == "rahul@client.com"


def test_normalize_contact_plain_text() -> None:
    assert normalize_contact("  ops team  ") == "ops team"
