"""Tests for ArtworkVerificationAgent."""

from agents.artwork_verification_agent import ArtworkVerificationAgent
from models.agent_result import AgentResult
from models.task import ArtworkSubmission
from supervisor.approval_policy import requires_human_approval

AGENT = ArtworkVerificationAgent()


def _submission(
    *,
    artwork_width: float,
    artwork_height: float,
    spec_width: float = 48.0,
    spec_height: float = 36.0,
    project_id: str = "PRJ-ART",
) -> ArtworkSubmission:
    return ArtworkSubmission(
        project_id=project_id,
        artwork_width_inches=artwork_width,
        artwork_height_inches=artwork_height,
        spec_width_inches=spec_width,
        spec_height_inches=spec_height,
        submitted_by="tester@example.com",
    )


def test_exact_match_is_match() -> None:
    """Zero difference should yield MATCH."""
    result = AGENT.execute(_submission(artwork_width=48.0, artwork_height=36.0))

    assert result.data["status"] == "MATCH"
    assert result.data["width_diff"] == 0.0
    assert result.data["height_diff"] == 0.0
    assert result.confidence == 1.0
    assert result.requires_approval is False


def test_within_tolerance_is_match() -> None:
    """0.1in off on width is within ±0.25in tolerance → MATCH."""
    result = AGENT.execute(_submission(artwork_width=48.1, artwork_height=36.0))

    assert result.data["status"] == "MATCH"
    assert result.data["width_diff"] == 0.1
    assert result.requires_approval is False
    assert "within tolerance" in result.reasoning.lower()


def test_exactly_at_tolerance_is_match() -> None:
    """Exactly 0.25in off uses <= tolerance, so status is MATCH."""
    result = AGENT.execute(_submission(artwork_width=48.25, artwork_height=36.0))

    assert result.data["status"] == "MATCH"
    assert result.data["width_diff"] == 0.25
    assert result.requires_approval is False


def test_just_over_tolerance_width_only_is_mismatch() -> None:
    """0.26in width mismatch should flag MISMATCH and mention width only."""
    result = AGENT.execute(_submission(artwork_width=48.26, artwork_height=36.0))

    assert result.data["status"] == "MISMATCH"
    assert result.data["width_diff"] == 0.26
    assert result.data["height_diff"] == 0.0
    assert result.requires_approval is True
    assert "Width mismatch" in result.reasoning
    assert "Height mismatch" not in result.reasoning


def test_both_dimensions_mismatched() -> None:
    """Both axes over tolerance should mention width and height."""
    result = AGENT.execute(
        _submission(
            artwork_width=48.5,
            artwork_height=36.5,
            spec_width=48.0,
            spec_height=36.0,
        )
    )

    assert result.data["status"] == "MISMATCH"
    assert result.requires_approval is True
    assert "Width mismatch" in result.reasoning
    assert "Height mismatch" in result.reasoning


def test_requires_approval_only_for_mismatch() -> None:
    """MATCH does not require approval; MISMATCH does."""
    match = AGENT.execute(_submission(artwork_width=48.0, artwork_height=36.0))
    mismatch = AGENT.execute(_submission(artwork_width=49.0, artwork_height=36.0))

    assert match.requires_approval is False
    assert mismatch.requires_approval is True


def test_approval_policy_mismatch_forces_true() -> None:
    """MISMATCH is in RISKY_STATUS_MAP for artwork_verification."""
    result = AgentResult(
        data={"project_id": "PRJ-X", "status": "MISMATCH", "width_diff": 0.5},
        confidence=1.0,
        requires_approval=True,
        reasoning="Width mismatch",
    )
    assert requires_human_approval("artwork_verification", result) is True


def test_approval_policy_match_does_not_force() -> None:
    """MATCH is not risky — high confidence + agent False returns False."""
    result = AgentResult(
        data={"project_id": "PRJ-Y", "status": "MATCH", "width_diff": 0.0},
        confidence=1.0,
        requires_approval=False,
        reasoning="within tolerance",
    )
    assert requires_human_approval("artwork_verification", result) is False
