"""Contract check: validate every data file in the fetched package against the schema it carries.

A non-conforming file or an unsupported schema major version fails the PR,
with output naming the cause.
"""

import importlib.util
import json
import jsonschema
import re
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest
import shutil

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / ".package"
DELIVERY_HISTORY_TAG = REPO_ROOT / "delivery-history.tag"
DESIGN_SYSTEM_VERSION_FILE = REPO_ROOT / "site" / "css" / "design-system.version"


def _load_setup():
    """Import tools/setup.py, which is a script rather than a package."""
    spec = importlib.util.spec_from_file_location(
        "setup", REPO_ROOT / "tools" / "setup.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = _load_setup()








def test_design_system_stylesheet_exists():
    """AC1: the design-system stylesheet is present under ./.package/."""
    css = setup.design_system_css(DESIGN_SYSTEM_VERSION_FILE.read_text().strip())
    assert css.is_file(), f"design-system CSS not found: {css}"




def test_build_check_exits_zero():
    """AC: build.py validates the package, renders the attempt chart, and writes the site to build/."""
    result = subprocess.run(
        [sys.executable, "build.py"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"build.py failed:\n{result.stdout}\n{result.stderr}"
    build_dir = REPO_ROOT / "build"
    assert (build_dir / "replay.html").is_file(), "build/replay.html missing"
    assert (build_dir / "story-journey.html").is_file(), "build/story-journey.html missing"
    assert (build_dir / "css" / "site.css").is_file(), "build/css/site.css missing"
    assert (build_dir / "css" / "design-system.version").is_file(), (
        "build/css/design-system.version missing"
    )
    assert (build_dir / "js" / "replay.js").is_file(), "build/js/replay.js missing"
    sprint_files = [
        f for f in build_dir.iterdir()
        if f.suffix == ".html" and f.name not in ("replay.html", "story-journey.html")
    ]
    assert sprint_files, "no sprint-overview page in build output"

    # Attempt-chart section structure in the rendered page
    page = sprint_files[0].read_text()
    assert "The Architect's split, story by story" in page, (
        "attempt chart heading not found in sprint-overview page"
    )
    assert "attempt-legend" in page, "attempt legend section not found"
    assert "attempt-row" in page, "attempt rows not found"
    assert "attempt-block" in page, "attempt blocks not found"

    # CSS: striped-blocked gradient present, no placeholder marker
    css = (build_dir / "css" / "site.css").read_text()
    assert "crew:placeholder" not in css, "crew:placeholder still present in site.css"
    assert "repeating-linear-gradient" in css, (
        "repeating-linear-gradient not found in site.css"
    )
    assert "--tone-blocked-text" in css, "--tone-blocked-text not in site.css"
    assert "--tone-blocked-bg" in css, "--tone-blocked-bg not in site.css"






def test_design_system_version_is_real():
    """AC5: the pinned version is real, a vX.Y.Z tag, and setup fetched the CSS for that tag."""
    raw = DESIGN_SYSTEM_VERSION_FILE.read_text()
    assert "crew:placeholder" not in raw, "design-system.version is a placeholder"
    version = raw.strip()
    assert re.fullmatch(r"v\d+\.\d+\.\d+", version), f"invalid tag format: {version}"
    css = setup.design_system_css(version)
    assert css.parent == PACKAGE_DIR, f"CSS for {version} is not under {PACKAGE_DIR}"
    assert css.is_file(), f"CSS for {version} not fetched: {css}"


def test_setup_fails_on_missing_release(monkeypatch, tmp_path):
    """AC6: setup exits non-zero and .package/ lacks the index when the release does not exist."""
    tag = "delivery-history-1999-01-01"

    def not_found(url, *args, **kwargs):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(setup, "PACKAGE_DIR", tmp_path)
    monkeypatch.setattr(setup.urllib.request, "urlopen", not_found)
    with pytest.raises(SystemExit) as exited:
        setup._download_delivery_history(tag)
    assert exited.value.code not in (0, None), (
        "setup should fail for a nonexistent release"
    )
    index = list(tmp_path.rglob("delivery-history.json"))
    assert not index, f"index file present after failed setup: {index}"


SUPPORTED_MAJOR_VERSIONS = (1, 2)


def _package_dir() -> Path:
    """Locate the package directory under ./.package/ named by delivery-history.tag."""
    tag = DELIVERY_HISTORY_TAG.read_text().strip()
    d = PACKAGE_DIR / tag
    assert d.is_dir(), f"package directory not found: {d}"
    return d


def _load_json(path: Path):
    """Load and parse a JSON file, asserting it exists."""
    assert path.is_file(), f"file not found: {path}"
    return json.loads(path.read_text())


def _validate_against_schema(data, schema, file_label: str):
    """Validate data against a JSON schema; raise ValueError naming the file on failure."""
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        messages = "; ".join(
            f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors[:5]
        )
        raise ValueError(f"{file_label} does not conform to its schema: {messages}")


def _check_schema_version(manifest: dict):
    """Assert the manifest's schema_version major is in SUPPORTED_MAJOR_VERSIONS."""
    version = manifest["schema_version"]
    match = re.fullmatch(r"(\d+)\.(\d+)(\.(\d+))?", version)
    assert match, f"unrecognized schema_version format: {version}"
    major = int(match.group(1))
    if major not in SUPPORTED_MAJOR_VERSIONS:
        raise ValueError(
            f"schema major version {major} is one the site cannot display "
            f"(supported: {SUPPORTED_MAJOR_VERSIONS})"
        )


def test_well_formed_package_passes():
    """AC1: a well-formed package on a supported major version passes validation."""
    pkg = _package_dir()

    manifest = _load_json(pkg / "manifest.json")
    _check_schema_version(manifest)

    manifest_schema = _load_json(pkg / "manifest.schema.json")
    index_schema = _load_json(pkg / "schema.json")
    events_schema = _load_json(pkg / "events.schema.json")

    _validate_against_schema(manifest, manifest_schema, "manifest.json")

    index = _load_json(pkg / "delivery-history.json")
    _validate_against_schema(index, index_schema, "delivery-history.json")

    events_dir = pkg / "events"
    if events_dir.is_dir():
        for events_file in sorted(events_dir.glob("*.json")):
            data = _load_json(events_file)
            _validate_against_schema(data, events_schema, f"events/{events_file.name}")


def test_non_conforming_file_fails_with_file_name():
    """AC2: a non-conforming data file causes a failure that names the file."""
    schema = {
        "type": "object",
        "required": ["sprint_id"],
        "properties": {
            "sprint_id": {"type": "string"},
        },
    }
    bad_data = {"events": []}

    with pytest.raises(ValueError) as exc_info:
        _validate_against_schema(bad_data, schema, "events/sprint-7.json")

    message = str(exc_info.value)
    assert "events/sprint-7.json" in message
    assert "does not conform" in message


def test_unsupported_major_version_fails_with_version():
    """AC3: a package on an unsupported major version fails, naming the version."""
    manifest = {"schema_version": "3.0.0"}

    with pytest.raises(ValueError) as exc_info:
        _check_schema_version(manifest)

    message = str(exc_info.value)
    assert "3" in message
    assert "cannot display" in message


def test_check_schema_version_accepts_major_2():
    """AC1: a manifest on schema major 2 passes the version gate without raising."""
    _check_schema_version({"schema_version": "2.0.0"})


def test_build_fails_on_unsupported_major_version():
    """AC2: build.py exits non-zero and names the major version as unsupported."""
    tag = "delivery-history-TEST"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "3.0.0", "package": "delivery-history", "date": "2026-01-01"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "delivery-history.json").write_text(json.dumps({}))

    original_tag = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")

    try:
        result = subprocess.run(
            [sys.executable, "build.py"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode != 0, "build.py should fail for unsupported major version"
        output = result.stdout + result.stderr
        assert "3" in output, f"output should name the major version: {output}"
        assert "cannot display" in output, (
            f"output should say the version is unsupported: {output}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)


def test_build_succeeds_on_well_formed_major_2_package():
    """AC3: a well-formed 2.0.0 package completes the build and writes the expected pages."""
    tag = "delivery-history-TEST-2"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "2.0.0", "package": "delivery-history", "date": "2026-11-06"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))

    index = {
        "package": "delivery-history",
        "schema_version": "2.0.0",
        "date": "2026-11-06",
        "timezone": "America/Chicago",
        "crew_repository": "crew",
        "repositories": ["crew-presentation"],
        "sprints": [
            {"name": "Sprint 1", "start": "2026-11-06", "end": "2026-11-06"}
        ],
        "cards": [
            {
                "repo": "crew-presentation",
                "number": 1,
                "type": "Story",
                "title": "A test story",
                "url": "https://github.com/mqucifer/crew-presentation/issues/1",
                "parent": None,
                "points": 1,
                "sprint": "Sprint 1",
                "status": "Done",
                "status_set": "2026-11-06T12:00:00Z",
                "created": "2026-11-06T09:00:00Z",
                "closed": "2026-11-06T12:00:00Z",
                "technical": False,
                "closed_as": "completed",
                "superseded_because": None,
            }
        ],
        "periods": [
            {
                "sprint": "Sprint 1",
                "start": "2026-11-06",
                "end": "2026-11-06",
                "file": "events/2026-11-06.json",
                "events": 1,
            }
        ],
        "analysis": {
            "sprints": [
                {
                    "sprint": "Sprint 1",
                    "as_of": "2026-11-06T23:59:59.999999-05:00",
                    "changed": [],
                    "attention": [],
                    "decided": [],
                }
            ],
            "stories": [
                {
                    "card": {"repo": "crew-presentation", "number": 1},
                    "pattern": "first_try",
                    "misses": 0,
                    "blocks": 0,
                    "escalations": 0,
                    "crew_fixes": [],
                    "repeated": None,
                    "delivered": "2026-11-06T12:00:00Z",
                    "wall_clock_seconds": 300,
                    "cost": None,
                    "text": "Merged.",
                }
            ],
            "deliveries": [],
        },
        "sprint_metrics": {
            "release": "2.0.0",
            "answers": {
                "Sprint 1": {
                    "cycle_time_days": 0,
                    "lead_time_days": 0,
                    "throughput": 1,
                    "wip_violations": 0,
                    "blocked_aging_days": 0,
                    "escalation_rate_percent": 0,
                    "points_delivered": 1,
                    "first_attempt_numerator": 1,
                    "first_attempt_denominator": 1,
                    "escalation_count": 0,
                    "superseded_count": 0,
                    "superseded_points": 0,
                    "first_attempt_rate_percent": 100,
                    "failure_breakdown": [],
                    "top_failure_causes": {},
                    "superseded_breakdown": None,
                    "flags": None,
                    "prior": None,
                    "delta": None,
                    "cycle_time_minutes": 30,
                    "lead_time_minutes": 30,
                }
            },
        },
    }
    (pkg_dir / "delivery-history.json").write_text(json.dumps(index))

    events_dir = pkg_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / "2026-11-06.json").write_text(
        json.dumps(
            {
                "events": [
                    {
                        "at": "2026-11-06T09:00:00Z",
                        "card": {"repo": "crew-presentation", "number": 1},
                        "from_column": "Inbox (Goals)",
                        "to_column": "Sprint Backlog",
                    }
                ]
            }
        )
    )

    original_tag = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")

    try:
        result = subprocess.run(
            [sys.executable, "build.py"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, (
            f"build.py should succeed for a well-formed 2.0.0 package:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        build_dir = REPO_ROOT / "build"
        assert (build_dir / "sprint-1.html").is_file(), (
            "sprint-overview page not written for 2.0.0 package"
        )
        assert (build_dir / "stories" / "crew-presentation-1.html").is_file(), (
            "story page not written for 2.0.0 package"
        )
        assert (build_dir / "replay.html").is_file(), (
            "replay page not written for 2.0.0 package"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)


def test_build_fails_on_non_conforming_data_file():
    """AC3: build.py exits non-zero and identifies the data file that failed to conform."""
    tag = "delivery-history-TEST"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "1.0.0", "package": "delivery-history", "date": "2026-01-01"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["sprints"],
                "properties": {"sprints": {"type": "array"}},
            }
        )
    )
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "delivery-history.json").write_text(json.dumps({"cards": []}))

    original_tag = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")

    try:
        result = subprocess.run(
            [sys.executable, "build.py"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode != 0, "build.py should fail for non-conforming data"
        output = result.stdout + result.stderr
        assert "delivery-history.json" in output, (
            f"output should name the failing file: {output}"
        )
        assert "does not conform" in output, (
            f"output should say the file does not conform: {output}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)


def test_placeholder_checks_contain_marker():
    """AC: the check files contain the assertions proving each acceptance criterion is exercised.

    A contract check: it reads the check modules and verifies the assertion
    markers for each AC are present, so a refactor that silently drops a check
    is caught here.
    """
    browser_test = REPO_ROOT / "tests" / "test_browser.py"
    assert browser_test.is_file(), "tests/test_browser.py not found"
    source = browser_test.read_text()

    # AC1: stat values match package data, design-system CSS from local file
    assert ".stat__value" in source, (
        "AC1: no assertion on .stat__value elements"
    )
    assert "stories delivered" in source, (
        "AC1: no assertion on the 'stories delivered' label"
    )
    assert "landed first try" in source, (
        "AC1: no assertion on the 'landed first try' label"
    )
    assert "--color-bg" in source, (
        "AC1: no assertion that design-system CSS was loaded"
    )

    # AC2: attempt chart rows match package stories in order
    assert ".attempt-row" in source, (
        "AC2: no assertion on .attempt-row elements"
    )
    assert "row_numbers" in source, (
        "AC2: no assertion extracting card numbers from rows"
    )

    # AC3: no console errors, header shows sprint name
    assert "console_errors" in source, (
        "AC3: no console error collection"
    )
    assert "sprint_name" in source, (
        "AC3: no assertion that header shows the sprint name"
    )

    # AC4: CSS custom properties resolve to light-theme values; IIFE sets data-theme
    assert "data-theme" in source, (
        "AC4: no assertion on data-theme attribute"
    )
    assert "--color-text" in source, (
        "AC4: no assertion on --color-text custom property"
    )

    # AC5: head order — IIFE before both stylesheet links
    assert "iife" in source, (
        "AC5: no assertion locating the theme IIFE script"
    )
    assert "LINK" in source, (
        "AC5: no assertion on <link> elements in head"
    )

    # AC6: exactly one .feature, one .stats, zero crew:placeholder
    assert ".feature" in source, (
        "AC6: no assertion on .feature element count"
    )
    assert ".stats" in source, (
        "AC6: no assertion on .stats element count"
    )
    assert "crew:placeholder" in source, (
        "AC6: no check for placeholder text in DOM"
    )

    # AC7: body background matches --color-bg for active theme
    assert "backgroundColor" in source, (
        "AC7: no assertion on body computed background"
    )

    # Token check: the site's own contrast and token checks (tools/token_check.py)
    # must contain the contrast-ratio computation and the raw-colour scan.
    token_check = REPO_ROOT / "tools" / "token_check.py"
    assert token_check.is_file(), "tools/token_check.py not found"
    tc = token_check.read_text()
    assert "contrast_ratio" in tc, (
        "token check has no contrast-ratio computation"
    )
    assert "0.2126" in tc, (
        "token check lacks the WCAG relative-luminance formula"
    )
    assert "find_raw_colours" in tc, "token check has no raw-colour scan"
    assert "#[0-9a-fA-F]" in tc, (
        "token check lacks the hex-colour pattern"
    )
