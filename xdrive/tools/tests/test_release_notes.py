"""release_notes.notes(): which changelog sections are releasable, and where a section ends."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from release_notes import CHANGELOG, notes  # noqa: E402

TEXT = """# Changelog

## xdrive-robotics [1.1.0] - Unreleased

### Added
- Something new.

## xdrive-robotics [1.0.0] - 2026-12-01

Based on ODrive v0.5.6.

### Added
- The first release.

## [0.5.6] - Unreleased

### Fixed
- An upstream fix.
"""


def test_returns_the_section_up_to_the_next_heading():
    assert notes(TEXT, "1.0.0") == "Based on ODrive v0.5.6.\n\n### Added\n- The first release."


def test_unreleased_section_is_refused():
    with pytest.raises(ValueError, match="Unreleased"):
        notes(TEXT, "1.1.0")


def test_missing_version_is_refused():
    with pytest.raises(ValueError, match="no '## xdrive-robotics \\[2.0.0\\]"):
        notes(TEXT, "2.0.0")


def test_upstream_sections_are_not_releases():
    with pytest.raises(ValueError, match="no '## xdrive-robotics \\[0.5.6\\]"):
        notes(TEXT, "0.5.6")


def test_empty_section_is_refused():
    with pytest.raises(ValueError, match="empty"):
        notes("## xdrive-robotics [1.0.0] - 2026-12-01\n\n## [0.5.6] - Unreleased\n", "1.0.0")


def test_repo_changelog_has_a_fork_section():
    assert "## xdrive-robotics [" in CHANGELOG.read_text()
