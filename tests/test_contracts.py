"""Contract check: validate the package structure fetched by setup.

This is the seed for the full validator that #60 upgrades.
It verifies that setup produced the expected layout.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / ".package"
DELIVERY_HISTORY_TAG = REPO_ROOT / "delivery-history.tag"
DESIGN_SYSTEM_VERSION_FILE = REPO_ROOT / "site" / "css" / "design-system.version"
DESIGN_SYSTEM_CSS = PACKAGE_DIR / "design-system.css"


def _read_delivery_history_tag() -> str:
    """Read the release tag from delivery-history.tag."""
    return DELIVERY_HISTORY_TAG.read_text().strip()


def test_package_index_file_exists():
    """AC1: the package's index file exists under ./.package/ after setup."""
    tag = _read_delivery_history_tag()
    index = PACKAGE_DIR / tag / "delivery-history.json"
    assert index.is_file(), f"package index not found: {index}"


def test_schema_file_exists():
    """AC1: the schema the package carries exists under ./.package/."""
    tag = _read_delivery_history_tag()
    schema = PACKAGE_DIR / tag / "schema.json"
    assert schema.is_file(), f"schema not found: {schema}"


def test_design_system_stylesheet_exists():
    """AC1: the design-system stylesheet is present under ./.package/."""
    assert DESIGN_SYSTEM_CSS.is_file(), f"design-system CSS not found: {DESIGN_SYSTEM_CSS}"


def test_manifest_parses_as_json():
    """AC1: the package's manifest.json parses as valid JSON."""
    tag = _read_delivery_history_tag()
    manifest_path = PACKAGE_DIR / tag / "manifest.json"
    assert manifest_path.is_file(), f"manifest not found: {manifest_path}"
    data = json.loads(manifest_path.read_text())
    assert "schema_version" in data, "manifest.json missing schema_version field"


def test_build_check_exits_zero():
    """AC2: the build check (python build.py) exits 0."""
    result = subprocess.run(
        [sys.executable, "build.py"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"build.py failed:\n{result.stdout}\n{result.stderr}"


def test_placeholder_checks_contain_marker():
    """AC3: build.py, test_browser.py, and test_tokens.py each contain crew:placeholder."""
    paths = [
        REPO_ROOT / "build.py",
        REPO_ROOT / "tests" / "test_browser.py",
        REPO_ROOT / "tests" / "test_tokens.py",
    ]
    for path in paths:
        content = path.read_text()
        assert "crew:placeholder" in content, f"{path} missing crew:placeholder"


def test_site_structure_contains_marker():
    """AC4: view templates, shared layout, replay player, and site CSS carry crew:placeholder."""
    paths = [
        REPO_ROOT / "site" / "templates" / "sprint_overview.html",
        REPO_ROOT / "site" / "templates" / "replay.html",
        REPO_ROOT / "site" / "templates" / "story_journey.html",
        REPO_ROOT / "site" / "templates" / "base.html",
        REPO_ROOT / "site" / "js" / "replay.js",
        REPO_ROOT / "site" / "css" / "site.css",
    ]
    for path in paths:
        content = path.read_text()
        assert "crew:placeholder" in content, f"{path} missing crew:placeholder"


def test_design_system_version_is_real():
    """AC5: design-system.version is not a placeholder, matches the tag form, and CSS was fetched for it."""
    content = DESIGN_SYSTEM_VERSION_FILE.read_text().strip()
    assert "crew:placeholder" not in content, "design-system.version is a placeholder"
    assert re.fullmatch(r"v\d+\.\d+\.\d+", content), f"invalid tag format: {content}"
    assert DESIGN_SYSTEM_CSS.is_file(), f"CSS for {content} not fetched: {DESIGN_SYSTEM_CSS}"


def test_setup_fails_on_missing_release():
    """AC6: setup exits non-zero and .package/ lacks the index when the release does not exist."""
    original = DELIVERY_HISTORY_TAG.read_text().strip()
    try:
        DELIVERY_HISTORY_TAG.write_text("delivery-history-1999-01-01\n")
        result = subprocess.run(
            [sys.executable, "tools/setup.py"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode != 0, "setup should fail for a nonexistent release"
        missing_index = PACKAGE_DIR / "delivery-history-1999-01-01" / "delivery-history.json"
        assert not missing_index.is_file(), "index file should not exist after failed setup"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original + "\n")
