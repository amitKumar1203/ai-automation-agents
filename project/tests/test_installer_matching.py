"""Tests for installer ranking logic."""

from integrations.installer_matching import rank_installers
from models.task import InstallerProfile


def test_rank_installers_prefers_exact_region_and_capacity() -> None:
    roster = [
        InstallerProfile(
            installer_id="1",
            name="Austin Signs",
            region="Austin, TX",
            capacity=5,
            active_jobs=2,
            email="a@example.com",
        ),
        InstallerProfile(
            installer_id="2",
            name="Chicago Team",
            region="Chicago, IL",
            capacity=4,
            active_jobs=1,
            email="b@example.com",
        ),
    ]
    ranked = rank_installers("Austin, TX", roster)
    assert ranked[0].installer.name == "Austin Signs"
    assert ranked[0].match_type == "exact_region"


def test_rank_installers_skips_full_capacity() -> None:
    roster = [
        InstallerProfile(
            installer_id="1",
            name="Full Team",
            region="Austin, TX",
            capacity=3,
            active_jobs=3,
            email="a@example.com",
        )
    ]
    assert rank_installers("Austin, TX", roster) == []
