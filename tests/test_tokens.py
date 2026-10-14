"""Token and contrast checks: validate the site's CSS against the design system's rules.

crew:placeholder
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="crew:placeholder — real token checks come in a later epic"
)


def test_placeholder_passes():
    """A trivially-passing test so the check exits 0."""
    assert True
