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
    """AC1: build.py validates the package and writes the site to build/."""
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


SUPPORTED_MAJOR_VERSIONS = (1,)


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
    manifest = {"schema_version": "2.0.0"}

    with pytest.raises(ValueError) as exc_info:
        _check_schema_version(manifest)

    message = str(exc_info.value)
    assert "2" in message
    assert "cannot display" in message


def test_build_fails_on_unsupported_major_version():
    """AC2: build.py exits non-zero and names the major version as unsupported."""
    tag = "delivery-history-TEST"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "2.0.0", "package": "delivery-history", "date": "2026-01-01"}
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
        assert "2" in output, f"output should name the major version: {output}"
        assert "cannot display" in output, (
            f"output should say the version is unsupported: {output}"
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
