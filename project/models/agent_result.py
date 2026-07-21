"""Result model returned by all agents."""

from dataclasses import dataclass


@dataclass
class AgentResult:
    """Standardized output from any agent execution."""

    data: dict
    confidence: float  # 0.0 to 1.0
    requires_approval: bool
    reasoning: str
