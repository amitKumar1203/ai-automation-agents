"""Task models for agent input data."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class EmailMessage:
    """A single message within an email thread."""

    sender: str  # "team" | "internal" | "client"
    timestamp: datetime
    text: str = ""
    sender_email: str = ""  # parsed From address (for client auto-ack)


@dataclass
class EmailThread:
    """An email conversation thread passed to the Email Reply Monitoring Agent."""

    thread_id: str
    messages: list[EmailMessage] = field(default_factory=list)
    subject: str = ""


@dataclass
class VendorQuoteRequest:
    """A vendor quote request tracked by the Vendor Follow-Up Agent."""

    vendor_name: str
    project_id: str
    request_sent_at: datetime
    quote_received: bool
    quote_received_at: Optional[datetime] = None
    monday_item_id: Optional[str] = None


@dataclass
class ProjectApproval:
    """A client-approved project checked by the Purchase Order Automation Agent."""

    project_id: str
    client_name: str
    approved_at: datetime
    po_exists: bool
    estimated_amount: float
    vendor_name: str
    salesforce_id: Optional[str] = None


@dataclass
class ArtworkSubmission:
    """Artwork dimensions submitted for numeric verification against project specs."""

    project_id: str
    artwork_width_inches: float
    artwork_height_inches: float
    spec_width_inches: float
    spec_height_inches: float
    submitted_by: str


@dataclass
class IntakeSubmission:
    """Freeform client inquiry submitted for LLM-powered classification."""

    submission_id: str
    submitted_by: str
    text: str
    submitted_at: datetime


@dataclass
class ProjectActivity:
    """A project monitored by the Automated Follow-Up Agent for stall risk."""

    project_id: str
    project_name: str
    last_activity_at: datetime
    stage: str = ""
    owner_email: str = ""
    monday_item_id: Optional[str] = None


@dataclass
class StorefrontProject:
    """A project checked by the Storefront Search agent for imagery."""

    project_id: str
    project_name: str
    store_address: str
    monday_item_id: Optional[str] = None
    existing_image_url: str = ""


@dataclass
class InstallerProfile:
    """An installer on the roster used by Installer Matching."""

    installer_id: str
    name: str
    region: str
    capacity: int
    active_jobs: int
    email: str = ""
    monday_item_id: Optional[str] = None


@dataclass
class InstallProject:
    """A project needing installer assignment."""

    project_id: str
    project_name: str
    install_region: str
    monday_item_id: Optional[str] = None
    assigned_installer: str = ""
    install_date: str = ""


@dataclass
class InstallMatchRequest:
    """Install project plus roster snapshot for one matching run."""

    project: InstallProject
    installers: list[InstallerProfile] = field(default_factory=list)
