"""Sample task data for API demos and local testing."""

from datetime import datetime, timedelta, timezone

from models.task import (
    EmailMessage,
    EmailThread,
    IntakeSubmission,
    ProjectApproval,
    VendorQuoteRequest,
)


def get_sample_threads(reference_time: datetime | None = None) -> list[EmailThread]:
    """Return sample email threads for demonstration.

    Args:
        reference_time: Base time for relative timestamps; defaults to UTC now.
    """
    now = reference_time or datetime.now(timezone.utc)

    return [
        EmailThread(
            thread_id="ORD-1042",
            subject="Order status",
            messages=[
                EmailMessage(
                    sender="client",
                    timestamp=now - timedelta(hours=30),
                    text="Hi, can you confirm my order status?",
                    sender_email="client@example.com",
                )
            ],
        ),
        EmailThread(
            thread_id="ORD-1043",
            subject="Quick thanks",
            messages=[
                EmailMessage(
                    sender="client",
                    timestamp=now - timedelta(hours=8),
                    text="Thanks for the quick response earlier!",
                    sender_email="client@example.com",
                )
            ],
        ),
        EmailThread(
            thread_id="ORD-1044",
            subject="PO approval",
            messages=[
                EmailMessage(
                    sender="client",
                    timestamp=now - timedelta(hours=72),
                    text="Is my PO approved yet?",
                    sender_email="client@example.com",
                ),
                EmailMessage(
                    sender="team",
                    timestamp=now - timedelta(hours=1),
                    text="Yes, PO approved and sent to vendor.",
                    sender_email="team@example.com",
                ),
            ],
        ),
    ]


def get_sample_vendor_requests(
    reference_time: datetime | None = None,
) -> list[VendorQuoteRequest]:
    """Return sample vendor quote requests covering all follow-up statuses.

    Args:
        reference_time: Base time for relative timestamps; defaults to UTC now.
    """
    now = reference_time or datetime.now(timezone.utc)

    return [
        VendorQuoteRequest(
            vendor_name="Acme Supplies",
            project_id="PRJ-2001",
            request_sent_at=now - timedelta(hours=72),
            quote_received=True,
            quote_received_at=now - timedelta(hours=24),
        ),
        VendorQuoteRequest(
            vendor_name="Omega Parts Co",
            project_id="PRJ-2002",
            request_sent_at=now - timedelta(hours=30),
            quote_received=False,
        ),
        VendorQuoteRequest(
            vendor_name="Delta Components",
            project_id="PRJ-2003",
            request_sent_at=now - timedelta(hours=60),
            quote_received=False,
        ),
        VendorQuoteRequest(
            vendor_name="Northwind Manufacturing",
            project_id="PRJ-2004",
            request_sent_at=now - timedelta(hours=110),
            quote_received=False,
        ),
    ]


def get_sample_project_approvals(
    reference_time: datetime | None = None,
) -> list[ProjectApproval]:
    """Return sample project approvals for PO automation demos.

    Args:
        reference_time: Base time for relative timestamps; defaults to UTC now.
    """
    now = reference_time or datetime.now(timezone.utc)

    return [
        ProjectApproval(
            project_id="PRJ-3001",
            client_name="Brightline Corp",
            approved_at=now - timedelta(days=14),
            po_exists=True,
            estimated_amount=12500.00,
            vendor_name="Acme Supplies",
        ),
        ProjectApproval(
            project_id="PRJ-3002",
            client_name="Horizon Labs",
            approved_at=now - timedelta(days=3),
            po_exists=False,
            estimated_amount=48250.50,
            vendor_name="Delta Components",
        ),
        ProjectApproval(
            project_id="PRJ-3003",
            client_name="Summit Retail",
            approved_at=now - timedelta(days=1),
            po_exists=False,
            estimated_amount=9750.00,
            vendor_name="Omega Parts Co",
        ),
        ProjectApproval(
            project_id="PRJ-3004",
            client_name="Northgate Industries",
            approved_at=now - timedelta(hours=12),
            po_exists=False,
            estimated_amount=210000.00,
            vendor_name="Northwind Manufacturing",
        ),
    ]


# Artwork submissions are entered via the dashboard (numeric / vision) —
# no hardcoded sample batch.


def get_sample_intake_submissions(
    reference_time: datetime | None = None,
) -> list[IntakeSubmission]:
    """Return varied client inquiries covering every intake category.

    The final example intentionally mixes project and pricing intent so Claude
    can demonstrate conservative confidence and human-review routing.
    """
    now = reference_time or datetime.now(timezone.utc)
    return [
        IntakeSubmission(
            submission_id="INT-5001",
            submitted_by="maya@northstarretail.com",
            text=(
                "We need new exterior signage for two locations opening in "
                "October. Can your team handle design, fabrication, and install?"
            ),
            submitted_at=now - timedelta(hours=18),
        ),
        IntakeSubmission(
            submission_id="INT-5002",
            submitted_by="Daniel Cho",
            text=(
                "Could you send a price estimate for replacing four lobby "
                "directory panels? We are comparing costs this week."
            ),
            submitted_at=now - timedelta(hours=10),
        ),
        IntakeSubmission(
            submission_id="INT-5003",
            submitted_by="facilities@brightline.example",
            text=(
                "The vinyl installed last month is already peeling at the "
                "corners, and one panel arrived scratched. Please help."
            ),
            submitted_at=now - timedelta(hours=6),
        ),
        IntakeSubmission(
            submission_id="INT-5004",
            submitted_by="Priya Shah",
            text=(
                "Do you serve the Denver area, and what are your normal "
                "business hours?"
            ),
            submitted_at=now - timedelta(hours=3),
        ),
        IntakeSubmission(
            submission_id="INT-5005",
            submitted_by="alex@riverwalk.example",
            text=(
                "We may need a new illuminated storefront sign around 12 feet "
                "wide. Before we decide, can you tell me roughly what that "
                "would cost and whether a September install is realistic?"
            ),
            submitted_at=now - timedelta(minutes=45),
        ),
    ]
