"""Verify the project skeleton is complete and well-formed."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_skeleton_files_exist():
    """Every structure-named file is present in the repository."""
    expected = [
        "build.py",
        "tests/test_contracts.py",
        "tests/test_browser.py",
        "tests/test_tokens.py",
        "tools/setup.py",
        "site/templates/base.html",
        "site/templates/sprint_overview.html",
        "site/templates/replay.html",
        "site/templates/story_journey.html",
        "site/js/replay.js",
        "site/css/design-system.version",
        "requirements.txt",
    ]
    for rel in expected:
        assert (REPO_ROOT / rel).exists(), f"missing: {rel}"
    css_files = list((REPO_ROOT / "site" / "css").glob("*.css"))
    assert css_files, "no CSS file found under site/css/"


def test_design_system_version_format():
    """design-system.version holds exactly one line: a release tag vX.Y.Z."""
    path = REPO_ROOT / "site" / "css" / "design-system.version"
    content = path.read_text()
    lines = content.strip().splitlines()
    assert len(lines) == 1, f"expected 1 line, got {len(lines)}"
    assert re.fullmatch(r"v\d+\.\d+\.\d+", lines[0]), (
        f"not a release tag vX.Y.Z: {lines[0]!r}"
    )
    assert "crew:placeholder" not in content


def test_requirements_pinned_with_hashes():
    """Every dependency in requirements.txt is pinned with == and carries a sha256 hash."""
    path = REPO_ROOT / "requirements.txt"
    lines = [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert lines, "requirements.txt is empty"
    for line in lines:
        assert re.search(r"^[a-zA-Z][a-zA-Z0-9_-]*==\d", line), (
            f"not pinned with ==: {line}"
        )
        assert ">=" not in line, f"uses >=: {line}"
        assert "~=" not in line, f"uses ~=: {line}"
        assert re.search(r"--hash=sha256:[0-9a-f]{64}", line), (
            f"missing --hash=sha256:<64-hex>: {line}"
        )


def test_placeholder_files_contain_token():
    """Each placeholder file contains the literal string crew:placeholder in a comment."""
    placeholder_files = [
        "build.py",
        "tests/test_browser.py",
        "tests/test_tokens.py",
        "site/templates/base.html",
        "site/templates/sprint_overview.html",
        "site/templates/replay.html",
        "site/templates/story_journey.html",
        "site/js/replay.js",
    ]
    for rel in placeholder_files:
        content = (REPO_ROOT / rel).read_text()
        assert "crew:placeholder" in content, f"missing crew:placeholder: {rel}"
    css_files = list((REPO_ROOT / "site" / "css").glob("*.css"))
    assert css_files, "no CSS file under site/css/"
    for css_file in css_files:
        assert "crew:placeholder" in css_file.read_text(), (
            f"missing crew:placeholder: {css_file.name}"
        )
