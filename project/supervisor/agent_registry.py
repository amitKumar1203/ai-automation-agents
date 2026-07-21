"""Agent registry for routing tasks to the correct agent."""

from agents.ai_mockup_agent import AIMockupAgent
from agents.ai_rendering_agent import AIRenderingAgent
from agents.artwork_verification_agent import ArtworkVerificationAgent
from agents.automated_followup_agent import AutomatedFollowUpAgent
from agents.base_agent import BaseAgent
from agents.email_reply_agent import EmailReplyMonitoringAgent
from agents.installation_qc_agent import InstallationQCAgent
from agents.intake_classification_agent import IntakeClassificationAgent
from agents.photo_analysis_agent import PhotoAnalysisAgent
from agents.po_automation_agent import POAutomationAgent
from agents.installer_matching_agent import InstallerMatchingAgent
from agents.storefront_search_agent import StorefrontSearchAgent
from agents.vendor_followup_agent import VendorFollowUpAgent

AGENT_REGISTRY: dict[str, BaseAgent] = {
    "email_reply_monitoring": EmailReplyMonitoringAgent(),
    "intake_classification": IntakeClassificationAgent(),
    "vendor_followup": VendorFollowUpAgent(),
    "po_automation": POAutomationAgent(),
    "artwork_verification": ArtworkVerificationAgent(),
    "automated_followup": AutomatedFollowUpAgent(),
    "storefront_search": StorefrontSearchAgent(),
    "installer_matching": InstallerMatchingAgent(),
    "ai_rendering": AIRenderingAgent(),
    "ai_mockup": AIMockupAgent(),
    "photo_analysis": PhotoAnalysisAgent(),
    "installation_qc": InstallationQCAgent(),
}


def register_agent(name: str, agent: BaseAgent) -> None:
    """Register an agent instance under the given name."""
    AGENT_REGISTRY[name] = agent


def get_agent(name: str) -> BaseAgent:
    """Return the agent registered under the given name.

    Raises:
        KeyError: If no agent is registered under ``name``.
    """
    if name not in AGENT_REGISTRY:
        registered = ", ".join(sorted(AGENT_REGISTRY)) or "(none)"
        raise KeyError(
            f"Agent '{name}' not found. Registered agents: {registered}"
        )
    return AGENT_REGISTRY[name]
