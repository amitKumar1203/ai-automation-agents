"""LLM-powered agent for classifying freeform client inquiries."""

from integrations.classification_client import (
    ClassificationConfigError,
    ClassificationError,
    classify_intake_text,
)
from agents.base_agent import BaseAgent
from models.agent_result import AgentResult
from models.task import IntakeSubmission


class IntakeClassificationAgent(BaseAgent):
    """Classify intake submissions and flag uncertain/high-stakes results."""

    def execute(self, task: IntakeSubmission) -> AgentResult:
        """Classify one submission without allowing API errors to abort a batch."""
        try:
            classification = classify_intake_text(task.text)
        except (ClassificationError, ClassificationConfigError) as exc:
            return AgentResult(
                data={
                    "submission_id": task.submission_id,
                    "category": "unclassified",
                    "submitted_by": task.submitted_by,
                },
                confidence=0.0,
                requires_approval=True,
                reasoning=(
                    "Classification failed and needs manual review: "
                    f"{exc}"
                ),
            )

        category = str(classification["category"])
        confidence = float(classification["confidence"])
        model_reasoning = str(classification["reasoning"])
        return AgentResult(
            data={
                "submission_id": task.submission_id,
                "category": category,
                "submitted_by": task.submitted_by,
            },
            confidence=confidence,
            requires_approval=(
                confidence < 0.75 or category == "support_issue"
            ),
            reasoning=(
                f"Classified as '{category}' (confidence: {confidence:.2f}): "
                f"{model_reasoning}"
            ),
        )
