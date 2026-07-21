"""Abstract base class for all agents in the supervisor system."""

from abc import ABC, abstractmethod
from typing import Any

from models.agent_result import AgentResult


class BaseAgent(ABC):
    """Common interface that every agent must implement."""

    @abstractmethod
    def execute(self, task: Any) -> AgentResult:
        """Run the agent logic on the given task and return a result."""
