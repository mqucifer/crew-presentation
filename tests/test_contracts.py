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
import time
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
    """AC: build.py validates the package, renders the sprint overview, and writes the site to build/."""
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "build.py"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    elapsed = time.monotonic() - start
    assert elapsed < 20, (
        f"build.py took {elapsed:.1f}s (limit 20s); "
        "events-file validation must not check every event against every oneOf branch"
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

    # Section structure of the rendered page, which the pinned package decides:
    # a 3.0.0 package carries no analysis, so the page renders the sprint's
    # stories story by story, grouped under their epics; a 2.x (or earlier)
    # package carries analysis with delivered stories, so the page renders the
    # attempt chart. test_browser holds the no-analysis
    # case (test_no_attempt_elements_when_no_analysis).
    index = _load_json(_package_dir() / "delivery-history.json")
    analysis_stories = index.get("analysis", {}).get("stories", [])
    has_delivered_story = any(story.get("delivered") for story in analysis_stories)

    page = sorted(sprint_files)[0].read_text()
    if has_delivered_story:
        # AC2: the package carries delivered analysis, so the page shows the
        # attempt chart.
        assert "Stories delivered this sprint" in page, (
            "sprint chart heading not found in sprint-overview page"
        )
        assert 'class="attempt-legend"' in page, "attempt legend section not found"
        assert 'class="attempt-row"' in page, "attempt rows not found"
        # attempt-block is always rendered alongside a modifier class, e.g.
        # class="attempt-block attempt-block--landed", so check the prefix.
        assert 'class="attempt-block' in page, "attempt blocks not found"
    else:
        # AC1: the package carries no analysis, so the page shows the sprint's
        # stories grouped under their epics, with a legend and attempt blocks
        # read from the sprint's events, but no attempt rows from the analysis
        # path.
        assert "What got done, story by story" in page, (
            "story-by-story heading not found in sprint-overview page"
        )
        assert 'class="attempt-legend"' in page, (
            "attempt legend not found without analysis"
        )
        assert 'class="attempt-row"' not in page, "attempt rows found without analysis"

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


def _make_package_tarball(tag: str) -> bytes:
    """A minimal tar.gz with the expected layout: <tag>/delivery-history.json."""
    import io
    import tarfile as _tarfile

    buf = io.BytesIO()
    with _tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = json.dumps({}).encode()
        info = _tarfile.TarInfo(name=f"{tag}/delivery-history.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _FakeResponse:
    """A context-manager response whose read() returns pre-captured bytes."""

    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_download_retries_on_transient_failure(monkeypatch, tmp_path):
    """AC1: a 504 on the first attempt, then success, lets setup complete as if nothing failed."""
    tag = "delivery-history-TEST-RETRY"
    tarball = _make_package_tarball(tag)
    calls = []

    def flaky(url, *args, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 504, "Gateway Timeout", None, None)
        return _FakeResponse(tarball)

    monkeypatch.setattr(setup, "PACKAGE_DIR", tmp_path)
    monkeypatch.setattr(setup.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(setup.time, "sleep", lambda x: None)

    setup._download_delivery_history(tag)

    assert len(calls) == 2, f"expected 2 attempts, got {len(calls)}"
    index = tmp_path / tag / "delivery-history.json"
    assert index.is_file(), f"index file not found: {index}"


def test_download_retries_on_connection_error(monkeypatch, tmp_path):
    """AC1: a connection error (not a 5xx) is also transient and retried."""
    tag = "delivery-history-TEST-CONN"
    tarball = _make_package_tarball(tag)
    calls = []

    def flaky(url, *args, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.URLError("Connection refused")
        return _FakeResponse(tarball)

    monkeypatch.setattr(setup, "PACKAGE_DIR", tmp_path)
    monkeypatch.setattr(setup.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(setup.time, "sleep", lambda x: None)

    setup._download_delivery_history(tag)

    assert len(calls) == 2
    index = tmp_path / tag / "delivery-history.json"
    assert index.is_file()


def test_download_stalled_read_is_retried(monkeypatch, tmp_path):
    """AC5: a stalled read (timeout) is treated as a transient failure and retried."""
    import socket

    tag = "delivery-history-TEST-STALL"
    tarball = _make_package_tarball(tag)
    calls = []

    def stall_then_succeed(url, *args, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise socket.timeout("timed out")
        return _FakeResponse(tarball)

    monkeypatch.setattr(setup, "PACKAGE_DIR", tmp_path)
    monkeypatch.setattr(setup.urllib.request, "urlopen", stall_then_succeed)
    monkeypatch.setattr(setup.time, "sleep", lambda x: None)

    setup._download_delivery_history(tag)

    assert len(calls) == 2
    index = tmp_path / tag / "delivery-history.json"
    assert index.is_file()


def test_download_fails_on_persistent_transient(monkeypatch, tmp_path, capsys):
    """AC3: when a server keeps failing, setup gives up after a finite number of attempts
    and the failure names the release it was fetching."""
    tag = "delivery-history-2026-11-08"
    calls = []

    def always_504(url, *args, **kwargs):
        calls.append(url)
        raise urllib.error.HTTPError(url, 504, "Gateway Timeout", None, None)

    monkeypatch.setattr(setup, "PACKAGE_DIR", tmp_path)
    monkeypatch.setattr(setup.urllib.request, "urlopen", always_504)
    monkeypatch.setattr(setup.time, "sleep", lambda x: None)

    with pytest.raises(SystemExit) as exited:
        setup._download_delivery_history(tag)

    assert exited.value.code not in (0, None)
    assert len(calls) == setup.MAX_ATTEMPTS, (
        f"expected exactly {setup.MAX_ATTEMPTS} attempts, got {len(calls)}"
    )
    err = capsys.readouterr().err
    assert tag in err, f"failure output should name the tag: {err!r}"
    index = list(tmp_path.rglob("delivery-history.json"))
    assert not index, f"index file present after failed setup: {index}"


def test_design_system_css_retries_on_transient_failure(monkeypatch, tmp_path):
    """AC4: the design-system CSS fetch gets the same retry: a 5xx on the first attempt
    followed by a success lets setup complete with the CSS in place."""
    version = "v0.1.0"
    css_content = b"/* design system */\nbody { margin: 0; }\n"
    calls = []

    def flaky(url, *args, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)
        return _FakeResponse(css_content)

    monkeypatch.setattr(setup, "PACKAGE_DIR", tmp_path)
    monkeypatch.setattr(setup.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(setup.time, "sleep", lambda x: None)

    setup._download_design_system_css(version)

    assert len(calls) == 2
    css_path = setup.design_system_css(version)
    assert css_path.is_file(), f"CSS not found: {css_path}"
    assert css_path.read_bytes() == css_content


def test_design_system_css_fails_on_persistent_transient(monkeypatch, tmp_path, capsys):
    """AC3 (CSS): when the server keeps failing, the CSS download fails after bounded
    attempts and names the version."""
    version = "v0.1.0"
    calls = []

    def always_503(url, *args, **kwargs):
        calls.append(url)
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)

    monkeypatch.setattr(setup, "PACKAGE_DIR", tmp_path)
    monkeypatch.setattr(setup.urllib.request, "urlopen", always_503)
    monkeypatch.setattr(setup.time, "sleep", lambda x: None)

    with pytest.raises(SystemExit) as exited:
        setup._download_design_system_css(version)

    assert exited.value.code not in (0, None)
    assert len(calls) == setup.MAX_ATTEMPTS
    err = capsys.readouterr().err
    assert version in err, f"failure output should name the version: {err!r}"
    css_path = setup.design_system_css(version)
    assert not css_path.is_file(), f"CSS file left behind after failure: {css_path}"


SUPPORTED_MAJOR_VERSIONS = (1, 2, 3, 4)


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
    manifest = {"schema_version": "5.0.0"}

    with pytest.raises(ValueError) as exc_info:
        _check_schema_version(manifest)

    message = str(exc_info.value)
    assert "5" in message
    assert "cannot display" in message


def test_check_schema_version_accepts_major_2():
    """AC1: a manifest on schema major 2 passes the version gate without raising."""
    _check_schema_version({"schema_version": "2.0.0"})


def test_check_schema_version_accepts_major_4():
    """AC2: a manifest on schema major 4 passes the version gate without raising."""
    _check_schema_version({"schema_version": "4.0.0"})


def test_build_succeeds_on_well_formed_major_4_package():
    """AC1: a well-formed 4.0.0 package completes the build and writes the expected pages."""
    tag = "delivery-history-TEST-4"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "4.0.0", "package": "delivery-history", "date": "2026-11-05"}
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
        assert result.returncode == 0, (
            f"build.py should succeed for a well-formed 4.0.0 package:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        build_dir = REPO_ROOT / "build"
        assert (build_dir / "replay.html").is_file(), (
            "replay page not written for 4.0.0 package"
        )
        assert (build_dir / "story-journey.html").is_file(), (
            "story-journey page not written for 4.0.0 package"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)


def test_build_succeeds_when_sprint_events_file_absent():
    """AC2: a sprint whose events file is absent from the package directory renders its page without error."""
    tag = "delivery-history-TEST-NOEVENTS"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "3.0.0", "package": "delivery-history", "date": "2026-11-06"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))

    index = {
        "package": "delivery-history",
        "schema_version": "3.0.0",
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
                "events": 0,
            }
        ],
        "sprint_metrics": {
            "release": "3.0.0",
            "answers": {
                "Sprint 1": {
                    "cycle_time_days": 0,
                    "lead_time_days": 0,
                    "throughput": 0,
                    "wip_violations": 0,
                    "blocked_aging_days": 0,
                    "escalation_rate_percent": 0,
                    "points_delivered": 0,
                    "first_attempt_numerator": 0,
                    "first_attempt_denominator": 0,
                    "escalation_count": 0,
                    "superseded_count": 0,
                    "superseded_points": 0,
                    "first_attempt_rate_percent": None,
                    "failure_breakdown": [],
                    "top_failure_causes": {},
                    "superseded_breakdown": None,
                    "flags": None,
                    "prior": None,
                    "delta": None,
                    "cycle_time_minutes": 0,
                    "lead_time_minutes": 0,
                }
            },
        },
    }
    (pkg_dir / "delivery-history.json").write_text(json.dumps(index))

    # Note: the events directory and file are intentionally NOT created.

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
            f"build.py should succeed when a sprint's events file is absent:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        build_dir = REPO_ROOT / "build"
        page_path = build_dir / "sprint-1.html"
        assert page_path.is_file(), (
            "sprint-overview page not written when events file is absent"
        )
        page = page_path.read_text()
        assert 'id="sent-back-h"' in page, "'Sent back' card heading not found"
        assert 'id="left-open-h"' in page, "'Left open' card heading not found"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)


def test_events_file_read_at_most_once():
    """AC1: each events file is read from disk at most once per build.

    Without a cache, _load_sprint_events is called up to 3 times per sprint
    in the render loop (for epic_groups, for decided, for sent_back), plus
    once in _build_board_state, and _load_all_events re-reads every events
    file again for story-journey pages. Each call re-reads and JSON-parses
    the same file from disk. With delivery-history-2026-11-11's larger event
    set, this redundant I/O pushes the total past the 20-second bound.
    """
    tag = "delivery-history-TEST-CACHE"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "3.0.0", "package": "delivery-history", "date": "2026-11-06"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))

    index = {
        "package": "delivery-history",
        "schema_version": "3.0.0",
        "date": "2026-11-06",
        "timezone": "America/Chicago",
        "crew_repository": "crew",
        "repositories": ["crew-presentation"],
        "sprints": [
            {"name": "Sprint 1", "start": "2026-11-06", "end": "2026-11-06"},
            {"name": "Sprint 2", "start": "2026-11-07", "end": "2026-11-07"},
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
            },
            {
                "repo": "crew-presentation",
                "number": 2,
                "type": "Story",
                "title": "Another story",
                "url": "https://github.com/mqucifer/crew-presentation/issues/2",
                "parent": None,
                "points": 1,
                "sprint": "Sprint 2",
                "status": "Done",
                "status_set": "2026-11-07T12:00:00Z",
                "created": "2026-11-07T09:00:00Z",
                "closed": "2026-11-07T12:00:00Z",
                "technical": False,
                "closed_as": "completed",
                "superseded_because": None,
            },
        ],
        "periods": [
            {
                "sprint": "Sprint 1",
                "start": "2026-11-06",
                "end": "2026-11-06",
                "file": "events/2026-11-06.json",
                "events": 1,
            },
            {
                "sprint": "Sprint 2",
                "start": "2026-11-07",
                "end": "2026-11-07",
                "file": "events/2026-11-07.json",
                "events": 1,
            },
        ],
        "sprint_metrics": {
            "release": "3.0.0",
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
                },
                "Sprint 2": {
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
                },
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
                        "kind": "card_moved",
                        "at": "2026-11-06T09:00:00Z",
                        "card": {"repo": "crew-presentation", "number": 1},
                        "from_column": "Inbox (Goals)",
                        "to_column": "Sprint Backlog",
                    }
                ]
            }
        )
    )
    (events_dir / "2026-11-07.json").write_text(
        json.dumps(
            {
                "events": [
                    {
                        "kind": "card_moved",
                        "at": "2026-11-07T09:00:00Z",
                        "card": {"repo": "crew-presentation", "number": 2},
                        "from_column": "Inbox (Goals)",
                        "to_column": "Sprint Backlog",
                    }
                ]
            }
        )
    )

    # Import build.py and instrument _load_json to count reads per file.
    spec = importlib.util.spec_from_file_location(
        "build_cache_test", REPO_ROOT / "build.py"
    )
    build_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_mod)

    # Clear the cache in case it was populated by module-level code.
    if hasattr(build_mod, "_events_file_cache"):
        build_mod._events_file_cache.clear()

    load_counts: dict[str, int] = {}
    original_load_json = build_mod._load_json

    def counting_load_json(path):
        key = str(path)
        load_counts[key] = load_counts.get(key, 0) + 1
        return original_load_json(path)

    build_mod._load_json = counting_load_json

    try:
        build_mod._render_pages(pkg_dir)
    finally:
        build_mod._load_json = original_load_json
        shutil.rmtree(pkg_dir, ignore_errors=True)

    # Each events file should have been read from disk at most once.
    for name in ("2026-11-06.json", "2026-11-07.json"):
        path_str = str(events_dir / name)
        count = load_counts.get(path_str, 0)
        assert count <= 1, (
            f"events/{name} was read {count} times from disk; "
            "each events file must be read at most once per build, "
            "because redundant re-reading pushes the build past its "
            "20-second bound with a large enough package"
        )


def test_events_validators_created_once():
    """AC1: events-file validation must not create a fresh set of validators for every file.

    Creating a Draft202012Validator per branch per events file multiplies the
    cost linearly with the number of events files. With delivery-history-
    2026-11-11's larger package, this pushes the build past its 20-second bound.
    The fix hoists validator creation out of the per-file loop, so the count
    is independent of how many events files the package carries.
    """
    tag = "delivery-history-TEST-VALIDATORS"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "3.0.0", "package": "delivery-history", "date": "2026-11-06"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))

    # Events schema with a discriminator mapping to two branches.
    events_schema = {
        "type": "object",
        "required": ["events"],
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "discriminator": {
                        "propertyName": "kind",
                        "mapping": {
                            "card_moved": "#/$defs/CardMoved",
                            "sent_back": "#/$defs/SentBack",
                        },
                    },
                    "oneOf": [{"$ref": "#/$defs/CardMoved"}, {"$ref": "#/$defs/SentBack"}],
                },
            }
        },
        "$defs": {
            "CardMoved": {
                "type": "object",
                "required": ["kind", "at"],
                "properties": {
                    "kind": {"const": "card_moved"},
                    "at": {"type": "string"},
                },
            },
            "SentBack": {
                "type": "object",
                "required": ["kind", "at"],
                "properties": {
                    "kind": {"const": "sent_back"},
                    "at": {"type": "string"},
                },
            },
        },
    }
    (pkg_dir / "events.schema.json").write_text(json.dumps(events_schema))
    (pkg_dir / "delivery-history.json").write_text(json.dumps({"sprints": [], "cards": []}))

    events_dir = pkg_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    # Three well-formed events files.
    for date in ("2026-11-06", "2026-11-07", "2026-11-08"):
        (events_dir / f"{date}.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "kind": "card_moved",
                            "at": f"{date}T09:00:00Z",
                            "card": {"repo": "crew-presentation", "number": 1},
                            "from_column": "Inbox (Goals)",
                            "to_column": "Sprint Backlog",
                        }
                    ]
                }
            )
        )

    # Import build.py and instrument Draft202012Validator to count
    # instantiations.
    spec = importlib.util.spec_from_file_location(
        "build_validators_test", REPO_ROOT / "build.py"
    )
    build_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_mod)

    validator_counts = []
    original_validator = jsonschema.Draft202012Validator

    def counting_validator(*args, **kwargs):
        validator_counts.append(1)
        return original_validator(*args, **kwargs)

    jsonschema.Draft202012Validator = counting_validator
    try:
        build_mod._validate_package(pkg_dir)
    finally:
        jsonschema.Draft202012Validator = original_validator
        shutil.rmtree(pkg_dir, ignore_errors=True)

    # The events schema has 2 branches, so the events path needs at most
    # 1 structural + 2 branch = 3 validators, created once and reused across
    # all events files. _validate_against_schema creates 1 each for the
    # manifest and the index = 2. The total must be at most 5, independent
    # of the number of events files.
    #
    # Without the fix, each events file creates its own structural validator
    # plus one per branch: 3 files × (1 + 2) = 9, plus the 2 for manifest
    # and index = 11.
    assert len(validator_counts) <= 5, (
        f"Draft202012Validator was instantiated {len(validator_counts)} times; "
        "the expected count is at most 5 (2 for manifest and index, plus 3 "
        "for the events branches), independent of the number of events files. "
        "Creating validators per file multiplies the cost linearly and pushes "
        "the build past its 20-second bound with a large enough package."
    )


def test_build_fails_on_unsupported_major_version():
    """AC2: build.py exits non-zero and names the major version as unsupported."""
    tag = "delivery-history-TEST"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "5.0.0", "package": "delivery-history", "date": "2026-01-01"}
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
        assert "5" in output, f"output should name the major version: {output}"
        assert "cannot display" in output, (
            f"output should say the version is unsupported: {output}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)


def test_build_succeeds_on_well_formed_major_3_package():
    """AC1: a well-formed 3.0.0 package completes the build and writes the expected pages."""
    tag = "delivery-history-TEST-3"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "3.0.0", "package": "delivery-history", "date": "2026-11-06"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))

    index = {
        "package": "delivery-history",
        "schema_version": "3.0.0",
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
            "release": "3.0.0",
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
            f"build.py should succeed for a well-formed 3.0.0 package:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        build_dir = REPO_ROOT / "build"
        assert (build_dir / "sprint-1.html").is_file(), (
            "sprint-overview page not written for 3.0.0 package"
        )
        assert (build_dir / "stories" / "crew-presentation-1.html").is_file(), (
            "story page not written for 3.0.0 package"
        )
        assert (build_dir / "replay.html").is_file(), (
            "replay page not written for 3.0.0 package"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)


def test_sprint_page_shows_story_list_without_analysis():
    """AC1: with no analysis in the package, the first sprint page shows the
    sprint's stories story by story, grouped under their epics, and no
    attempt-chart elements (the case a 3.0.0 pin takes)."""
    tag = "delivery-history-TEST-3-NOANALYSIS"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "3.0.0", "package": "delivery-history", "date": "2026-11-06"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))

    index = {
        "package": "delivery-history",
        "schema_version": "3.0.0",
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
        "sprint_metrics": {
            "release": "3.0.0",
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
                    "roster": {"completed_stories": ["crew-presentation#1"]},
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
            f"build.py should succeed for a no-analysis 3.0.0 package:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        build_dir = REPO_ROOT / "build"
        page = (build_dir / "sprint-1.html").read_text()
        # The story-by-story heading, not the attempt chart's heading.
        assert "What got done, story by story" in page, (
            "story-by-story heading not found without analysis"
        )
        assert "Stories delivered this sprint" not in page, (
            "attempt-chart heading found without analysis"
        )
        # The sprint's story appears as a row under its epic group. Its parent is
        # null, so it sits under the 'not part of an epic' group.
        assert 'class="story-row"' in page, "story row not found without analysis"
        assert "not part of an epic" in page, (
            "'not part of an epic' group not found for a parentless story"
        )
        # The roster names the story delivered, so the group carries a done count.
        assert "1 of 1 stories done" in page, "done count not found"
        assert 'class="attempt-legend"' in page, (
            "attempt legend not found without analysis"
        )
        assert 'class="attempt-row"' not in page, "attempt rows found without analysis"
        assert 'class="attempt-block' not in page, (
            "attempt blocks found without events"
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


def test_build_fails_on_non_conforming_events_file():
    """AC3: build.py exits non-zero and names the events file that failed to conform.

    The events schema carries a discriminator, so build's fast path selects
    the branch by kind. An event missing a field its kind requires is
    rejected, not accepted on trust.
    """
    tag = "delivery-history-TEST-EVENTS"
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
    (pkg_dir / "schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["sprints"],
                "properties": {"sprints": {"type": "array"}},
            }
        )
    )
    # Events schema with a discriminator: the fast path will route each event
    # to its branch. The CardMoved branch requires both "kind" and "at".
    events_schema = {
        "type": "object",
        "required": ["events"],
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "discriminator": {
                        "propertyName": "kind",
                        "mapping": {"card_moved": "#/$defs/CardMoved"},
                    },
                    "oneOf": [{"$ref": "#/$defs/CardMoved"}],
                },
            }
        },
        "$defs": {
            "CardMoved": {
                "type": "object",
                "required": ["kind", "at"],
                "properties": {
                    "kind": {"const": "card_moved"},
                    "at": {"type": "string"},
                },
            }
        },
    }
    (pkg_dir / "events.schema.json").write_text(json.dumps(events_schema))
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps({"sprints": [], "cards": []})
    )

    # An events file whose event is missing the "at" field required by CardMoved.
    events_dir = pkg_dir / "events"
    events_dir.mkdir()
    (events_dir / "2026-01-01.json").write_text(
        json.dumps(
            {
                "package": "delivery-history",
                "schema_version": "3.0.0",
                "sprint": "Sprint 1",
                "start": "2026-01-01",
                "end": "2026-01-01",
                "events": [
                    {"kind": "card_moved"},  # missing "at"
                ],
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
        assert result.returncode != 0, "build.py should fail for non-conforming events file"
        output = result.stdout + result.stderr
        assert "events/2026-01-01.json" in output, (
            f"output should name the failing events file: {output}"
        )
        assert "does not conform" in output, (
            f"output should say the file does not conform: {output}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)


def test_build_fails_on_unrecognized_event_kind():
    """AC2: build.py exits non-zero and names the unrecognized kind when an event's
    kind value is absent from the schema's discriminator mapping."""
    tag = "delivery-history-TEST-UNRECOGNIZED"
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
    (pkg_dir / "schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["sprints"],
                "properties": {"sprints": {"type": "array"}},
            }
        )
    )
    # Events schema with a discriminator: only "card_moved" is in the mapping.
    events_schema = {
        "type": "object",
        "required": ["events"],
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "discriminator": {
                        "propertyName": "kind",
                        "mapping": {"card_moved": "#/$defs/CardMoved"},
                    },
                    "oneOf": [{"$ref": "#/$defs/CardMoved"}],
                },
            }
        },
        "$defs": {
            "CardMoved": {
                "type": "object",
                "required": ["kind", "at"],
                "properties": {
                    "kind": {"const": "card_moved"},
                    "at": {"type": "string"},
                },
            }
        },
    }
    (pkg_dir / "events.schema.json").write_text(json.dumps(events_schema))
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps({"sprints": [], "cards": []})
    )

    # An events file whose event has a kind not present in the discriminator mapping.
    events_dir = pkg_dir / "events"
    events_dir.mkdir()
    (events_dir / "2026-01-01.json").write_text(
        json.dumps(
            {
                "events": [
                    {"kind": "nonexistent_kind", "at": "2026-01-01T09:00:00Z"},
                ],
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
        assert result.returncode == 1, (
            f"build.py should exit 1 for an unrecognized kind, "
            f"got {result.returncode}\n{result.stdout}\n{result.stderr}"
        )
        assert "unrecognized kind" in result.stderr, (
            f"stderr should contain 'unrecognized kind': {result.stderr}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)


def _sent_back_package(sent_back_events: list[dict], sprint_name: str = "Sprint 1") -> dict:
    """A minimal 3.0.0 package index with the given sent_back events."""
    return {
        "package": "delivery-history",
        "schema_version": "3.0.0",
        "date": "2026-11-06",
        "timezone": "America/Chicago",
        "crew_repository": "crew",
        "repositories": ["crew-presentation"],
        "sprints": [
            {"name": sprint_name, "start": "2026-11-06", "end": "2026-11-06"}
        ],
        "cards": [],
        "periods": [
            {
                "sprint": sprint_name,
                "start": "2026-11-06",
                "end": "2026-11-06",
                "file": "events/2026-11-06.json",
                "events": len(sent_back_events),
            }
        ],
        "sprint_metrics": {
            "release": "3.0.0",
            "answers": {
                sprint_name: {
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


def _build_with_sent_back(events: list[dict]) -> str:
    """Build a site from a package carrying the given events; return the sprint page."""
    tag = "delivery-history-TEST-SENTBACK"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "3.0.0", "package": "delivery-history", "date": "2026-11-06"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))
    index = _sent_back_package(events)
    (pkg_dir / "delivery-history.json").write_text(json.dumps(index))

    events_dir = pkg_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / "2026-11-06.json").write_text(json.dumps({"events": events}))

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
            f"build.py should succeed:\n{result.stdout}\n{result.stderr}"
        )
        page = (REPO_ROOT / "build" / "sprint-1.html").read_text()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)
    return page


def test_sent_back_card_shows_count_and_rows():
    """AC1: the card head's count equals the number of rows, one per sent_back event."""
    events = [
        {
            "kind": "sent_back",
            "at": "2026-11-06T10:00:00Z",
            "repo": "crew-presentation",
            "card": {"repo": "crew-presentation", "number": 100},
            "sent_from": "review",
            "sent_to": "build",
            "rule": "gate.review_changes_requested",
            "round": 1,
            "counts": {"findings": 1},
        },
        {
            "kind": "sent_back",
            "at": "2026-11-06T11:00:00Z",
            "repo": "crew-presentation",
            "card": {"repo": "crew-presentation", "number": 101},
            "sent_from": "gate",
            "sent_to": "build",
            "rule": "gate.findings_at_done",
            "round": 1,
            "counts": {"findings": 2},
        },
        {
            "kind": "sent_back",
            "at": "2026-11-06T12:00:00Z",
            "repo": "crew-presentation",
            "card": {"repo": "crew-presentation", "number": 102},
            "sent_from": "ci",
            "sent_to": "build",
            "rule": "gate.ci_before_review",
            "round": 1,
            "counts": {"jobs": 1},
        },
    ]
    page = _build_with_sent_back(events)
    assert 'id="sent-back-h"' in page, "'Sent back' card heading not found"
    assert "3 times" in page, "card head count should be '3 times'"
    # One row per sent_back event
    assert page.count('class="sent-back-row"') == 3, (
        "expected 3 sent-back rows, one per event"
    )


def test_sent_back_row_shows_card_number_steps_reason_time():
    """AC2: a row shows the card number, steps in the board's words, a plain reason, and the time."""
    events = [
        {
            "kind": "sent_back",
            "at": "2026-11-06T22:48:00Z",
            "repo": "crew-presentation",
            "card": {"repo": "crew-presentation", "number": 136},
            "sent_from": "review",
            "sent_to": "build",
            "rule": "gate.review_changes_requested",
            "round": 1,
            "counts": {"findings": 1},
        },
    ]
    page = _build_with_sent_back(events)
    # Card number
    assert "#136" in page, "card number not shown"
    # Steps in the board's own words
    assert "review" in page, "sent_from step not named in the board's words"
    assert "building" in page, "sent_to step not named in the board's words"
    # Plain sentence (not a raw rule code)
    assert "asked for changes" in page, "reason should be a plain sentence"
    # Time
    assert "22:48" in page, "time not shown"


def test_sent_back_no_raw_rule_code_on_page():
    """AC3: no raw machine code (rule) appears on the page."""
    events = [
        {
            "kind": "sent_back",
            "at": "2026-11-06T10:00:00Z",
            "repo": "crew-presentation",
            "card": {"repo": "crew-presentation", "number": 100},
            "sent_from": "gate",
            "sent_to": "build",
            "rule": "gate.findings_at_done",
            "round": 1,
            "counts": {"findings": 1},
        },
        {
            "kind": "sent_back",
            "at": "2026-11-06T11:00:00Z",
            "repo": "crew-presentation",
            "card": None,
            "sent_from": "review",
            "sent_to": "design",
            "rule": "gate.design_refused",
            "round": None,
            "counts": {},
        },
    ]
    page = _build_with_sent_back(events)
    assert "gate.findings_at_done" not in page, "raw rule code visible on page"
    assert "gate.design_refused" not in page, "raw rule code visible on page"
    assert "sent_back" not in page.replace("Sent back", "").replace("sent-back", ""), (
        "raw event kind visible on page"
    )


def test_sent_back_no_card_reads_as_design():
    """AC4: a send-back with no card reads as the project's design being sent back."""
    events = [
        {
            "kind": "sent_back",
            "at": "2026-11-06T21:49:00Z",
            "repo": "crew-presentation",
            "card": None,
            "sent_from": "review",
            "sent_to": "design",
            "rule": "gate.design_refused",
            "round": None,
            "counts": {},
        },
    ]
    page = _build_with_sent_back(events)
    # No card number shown
    assert "sent-back-row__number" not in page, (
        "no-card row should not show a story number"
    )
    # Reads as design sent back
    assert "A design was refused at review" in page, (
        "no-card row should read as the design being sent back"
    )
    assert "back to design" in page, "sent_to step not named"
    # Time shown
    assert "21:49" in page, "time not shown"


def test_sent_back_unknown_step_still_renders():
    """AC5: an unknown step name reads as a step, the row is not dropped."""
    events = [
        {
            "kind": "sent_back",
            "at": "2026-11-06T10:00:00Z",
            "repo": "crew-presentation",
            "card": {"repo": "crew-presentation", "number": 100},
            "sent_from": "some_new_step",
            "sent_to": "build",
            "rule": "some_unknown_rule",
            "round": 1,
            "counts": {},
        },
    ]
    page = _build_with_sent_back(events)
    assert 'id="sent-back-h"' in page, "'Sent back' card heading not found"
    assert "1 times" in page, "count should be 1"
    assert page.count('class="sent-back-row"') == 1, "row should not be dropped"
    # Unknown step reads as a step (underscores replaced with spaces)
    assert "some new step" in page, "unknown step should read as a step"
    # Known step renders in the board's own word
    assert "building" in page, "known step should render in the board's word"


def test_sent_back_empty_shows_plain_words():
    """AC6: a sprint with no sent_back events says so in plain words, never blank or 0."""
    events = [
        {
            "kind": "card_moved",
            "at": "2026-11-06T09:00:00Z",
            "card": {"repo": "crew-presentation", "number": 1},
            "from_column": "Inbox (Goals)",
            "to_column": "Sprint Backlog",
            "by": "crew",
        }
    ]
    page = _build_with_sent_back(events)
    assert 'id="sent-back-h"' in page, "'Sent back' card heading not found"
    # No count of 0
    assert "0 times" not in page, "should not show a count of 0"
    # Plain words saying no send-backs
    assert "No send-backs recorded" in page, (
        "should say in plain words that no send-backs are recorded"
    )
    # No rows
    assert 'class="sent-back-row"' not in page, "no rows should be rendered"


def test_sent_back_pinned_package_builds():
    """AC7: the pinned package builds and the sent-back card is populated from events alone."""
    result = subprocess.run(
        [sys.executable, "build.py"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"build failed:\n{result.stdout}\n{result.stderr}"
    build_dir = REPO_ROOT / "build"
    sprint_files = [
        f for f in build_dir.iterdir()
        if f.suffix == ".html" and f.name not in ("replay.html", "story-journey.html")
    ]
    assert sprint_files, "no sprint pages in build output"
    # Every sprint page has the 'Sent back' card
    for f in sprint_files:
        page = f.read_text()
        assert 'id="sent-back-h"' in page, (
            f"{f.name}: 'Sent back' card heading not found"
        )


def _left_open_package(
    events: list[dict], cards: list[dict], sprint_name: str = "Sprint 1"
) -> dict:
    """A minimal 3.0.0 package index with the given events and cards."""
    return {
        "package": "delivery-history",
        "schema_version": "3.0.0",
        "date": "2026-11-06",
        "timezone": "America/Chicago",
        "crew_repository": "crew",
        "repositories": ["crew-presentation"],
        "sprints": [
            {"name": sprint_name, "start": "2026-11-06", "end": "2026-11-06"}
        ],
        "cards": cards,
        "periods": [
            {
                "sprint": sprint_name,
                "start": "2026-11-06",
                "end": "2026-11-06",
                "file": "events/2026-11-06.json",
                "events": len(events),
            }
        ],
        "sprint_metrics": {
            "release": "3.0.0",
            "answers": {
                sprint_name: {
                    "cycle_time_days": 0,
                    "lead_time_days": 0,
                    "throughput": 0,
                    "wip_violations": 0,
                    "blocked_aging_days": 0,
                    "escalation_rate_percent": 0,
                    "points_delivered": 0,
                    "first_attempt_numerator": 0,
                    "first_attempt_denominator": 0,
                    "escalation_count": 0,
                    "superseded_count": 0,
                    "superseded_points": 0,
                    "first_attempt_rate_percent": 0,
                    "failure_breakdown": [],
                    "top_failure_causes": {},
                    "superseded_breakdown": None,
                    "flags": None,
                    "prior": None,
                    "delta": None,
                    "cycle_time_minutes": 0,
                    "lead_time_minutes": 0,
                }
            },
        },
    }


def _build_with_left_open(
    events: list[dict], cards: list[dict]
) -> str:
    """Build a site from a package carrying the given events and cards; return the sprint page."""
    tag = "delivery-history-TEST-LEFTOPEN"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "3.0.0", "package": "delivery-history", "date": "2026-11-06"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))
    index = _left_open_package(events, cards)
    (pkg_dir / "delivery-history.json").write_text(json.dumps(index))

    events_dir = pkg_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / "2026-11-06.json").write_text(json.dumps({"events": events}))

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
            f"build.py should succeed:\n{result.stdout}\n{result.stderr}"
        )
        page = (REPO_ROOT / "build" / "sprint-1.html").read_text()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)
    return page


def test_left_open_shows_stories_not_done_at_sprint_end():
    """AC1: stories not in Done at the sprint's end get rows; stories that reached Done do not; epics and goals do not."""
    cards = [
        {"repo": "crew-presentation", "number": 1, "type": "Story", "title": "Story one"},
        {"repo": "crew-presentation", "number": 2, "type": "Story", "title": "Story two"},
        {"repo": "crew-presentation", "number": 3, "type": "Epic", "title": "An epic"},
        {"repo": "crew-presentation", "number": 4, "type": "Goal", "title": "A goal"},
        {"repo": "crew-presentation", "number": 5, "type": "Story", "title": "Story five"},
    ]
    events = [
        # Story 1 ends in In Progress
        {"kind": "card_moved", "at": "2026-11-06T10:00:00Z",
         "card": {"repo": "crew-presentation", "number": 1},
         "from_column": "Ready", "to_column": "In Progress"},
        # Story 2 ends in Done
        {"kind": "card_moved", "at": "2026-11-06T09:00:00Z",
         "card": {"repo": "crew-presentation", "number": 2},
         "from_column": "Ready", "to_column": "In Progress"},
        {"kind": "card_moved", "at": "2026-11-06T11:00:00Z",
         "card": {"repo": "crew-presentation", "number": 2},
         "from_column": "In Progress", "to_column": "Done"},
        # Epic 3 ends in Ready (should NOT get a row)
        {"kind": "card_moved", "at": "2026-11-06T10:00:00Z",
         "card": {"repo": "crew-presentation", "number": 3},
         "from_column": "Inbox (Goals)", "to_column": "Ready"},
        # Goal 4 ends in Sprint Backlog (should NOT get a row)
        {"kind": "card_moved", "at": "2026-11-06T10:00:00Z",
         "card": {"repo": "crew-presentation", "number": 4},
         "from_column": "Inbox (Goals)", "to_column": "Sprint Backlog"},
        # Story 5 ends in Reviewing (should get a row)
        {"kind": "card_moved", "at": "2026-11-06T12:00:00Z",
         "card": {"repo": "crew-presentation", "number": 5},
         "from_column": "In Progress", "to_column": "Reviewing"},
    ]
    page = _build_with_left_open(events, cards)
    assert 'id="left-open-h"' in page, "'Left open at the end' card heading not found"
    # Story 1 and Story 5 get rows
    assert "#1" in page, "Story 1 should have a row"
    assert "#5" in page, "Story 5 should have a row"
    assert "Story one" in page, "Story 1 title should be shown"
    assert "Story five" in page, "Story 5 title should be shown"
    # Story 2 reached Done, so no row
    assert "#2" not in page or "Story two" not in page, (
        "Story 2 reached Done and should not have a row"
    )
    # Epic and Goal do not get rows
    assert "An epic" not in page, "Epic should not have a row"
    assert "A goal" not in page, "Goal should not have a row"
    # Exactly 2 rows
    assert page.count('class="left-open-row"') == 2, (
        "expected exactly 2 left-open rows"
    )


def test_left_open_badge_blocked_for_blocked_column():
    """AC2: a story in the Blocked column gets a 'Blocked' badge in the blocked tone."""
    cards = [
        {"repo": "crew-presentation", "number": 10, "type": "Story", "title": "Blocked story"},
    ]
    events = [
        {"kind": "card_moved", "at": "2026-11-06T14:00:00Z",
         "card": {"repo": "crew-presentation", "number": 10},
         "from_column": "In Progress", "to_column": "Blocked"},
    ]
    page = _build_with_left_open(events, cards)
    assert 'data-tone="blocked"' in page, "blocked badge should use the blocked tone"
    assert ">Blocked<" in page, "badge label should be 'Blocked'"


def test_left_open_badge_refused_for_send_back_move():
    """AC2: a story whose last move into its column was a send-back gets a 'Refused' badge in the blocked tone."""
    cards = [
        {"repo": "crew-presentation", "number": 20, "type": "Story", "title": "Refused story"},
    ]
    events = [
        # The card_moved event and sent_back event at the same second
        {"kind": "card_moved", "at": "2026-11-06T15:00:00Z",
         "card": {"repo": "crew-presentation", "number": 20},
         "from_column": "Reviewing", "to_column": "In Progress"},
        {"kind": "sent_back", "at": "2026-11-06T15:00:00Z",
         "repo": "crew-presentation",
         "card": {"repo": "crew-presentation", "number": 20},
         "sent_from": "review", "sent_to": "build",
         "rule": "gate.review_changes_requested",
         "round": 1, "counts": {"findings": 1}},
    ]
    page = _build_with_left_open(events, cards)
    assert 'data-tone="blocked"' in page, "refused badge should use the blocked tone"
    assert ">Refused<" in page, "badge label should be 'Refused'"


def test_left_open_badge_waiting_for_other_columns():
    """AC2: a story in a column other than Blocked, not moved by a send-back, gets a 'Waiting' badge in the waiting tone."""
    cards = [
        {"repo": "crew-presentation", "number": 30, "type": "Story", "title": "Waiting story"},
    ]
    events = [
        {"kind": "card_moved", "at": "2026-11-06T16:00:00Z",
         "card": {"repo": "crew-presentation", "number": 30},
         "from_column": "Ready", "to_column": "In Progress"},
    ]
    page = _build_with_left_open(events, cards)
    assert 'data-tone="waiting"' in page, "waiting badge should use the waiting tone"
    assert ">Waiting<" in page, "badge label should be 'Waiting'"


def test_left_open_row_shows_repo_number_title_and_duration():
    """AC3: a row shows the story's repository, number, title, and duration with a unit."""
    cards = [
        {"repo": "crew-presentation", "number": 40, "type": "Story", "title": "Duration story"},
    ]
    events = [
        # Moved at 10:00, sprint ends at 2026-11-07 00:00 UTC
        # Duration = 14 hours
        {"kind": "card_moved", "at": "2026-11-06T10:00:00Z",
         "card": {"repo": "crew-presentation", "number": 40},
         "from_column": "Ready", "to_column": "In Progress"},
    ]
    page = _build_with_left_open(events, cards)
    assert "crew-presentation" in page, "repository should be shown"
    assert "#40" in page, "number should be shown"
    assert "Duration story" in page, "title should be shown"
    # Duration: 14 hours (sprint ends at 2026-11-07T00:00:00Z, moved at 2026-11-06T10:00:00Z)
    assert "for 14 hours" in page, "duration should read 'for 14 hours'"


def test_left_open_duration_counts_back_before_sprint_start():
    """AC4: a story moved before the sprint started counts from that earlier move, not clamped at the sprint's start."""
    cards = [
        {"repo": "crew-presentation", "number": 50, "type": "Story", "title": "Early story"},
    ]
    events = [
        # Moved at 2026-11-04T12:00:00Z (2 days before the sprint's end date 2026-11-06)
        # Duration = 2026-11-07T00:00:00Z - 2026-11-04T12:00:00Z = 60 hours = 2 days 12 hours
        # Should read "for 2 days"
        {"kind": "card_moved", "at": "2026-11-04T12:00:00Z",
         "card": {"repo": "crew-presentation", "number": 50},
         "from_column": "Ready", "to_column": "In Progress"},
    ]
    page = _build_with_left_open(events, cards)
    # 60 hours = 2 days + 12 hours → "for 2 days"
    assert "for 2 days" in page, (
        "duration should count back from the earlier move, not clamp at sprint start"
    )


def test_left_open_empty_says_nothing_left_open():
    """AC5: a sprint with every story in Done says so in plain words, never a blank card."""
    cards = [
        {"repo": "crew-presentation", "number": 60, "type": "Story", "title": "Done story"},
    ]
    events = [
        {"kind": "card_moved", "at": "2026-11-06T09:00:00Z",
         "card": {"repo": "crew-presentation", "number": 60},
         "from_column": "Ready", "to_column": "In Progress"},
        {"kind": "card_moved", "at": "2026-11-06T12:00:00Z",
         "card": {"repo": "crew-presentation", "number": 60},
         "from_column": "In Progress", "to_column": "Done"},
    ]
    page = _build_with_left_open(events, cards)
    assert 'id="left-open-h"' in page, "'Left open at the end' card heading should always be present"
    assert "Nothing was left open" in page, (
        "should say in plain words that nothing was left open"
    )
    assert 'class="left-open-row"' not in page, "no rows should be rendered"


def test_left_open_pinned_package_builds():
    """AC1 (pinned): the pinned package builds and every sprint page has the left-open card."""
    result = subprocess.run(
        [sys.executable, "build.py"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"build failed:\n{result.stdout}\n{result.stderr}"
    build_dir = REPO_ROOT / "build"
    sprint_files = [
        f for f in build_dir.iterdir()
        if f.suffix == ".html" and f.name not in ("replay.html", "story-journey.html")
    ]
    assert sprint_files, "no sprint pages in build output"
    for f in sprint_files:
        page = f.read_text()
        assert 'id="left-open-h"' in page, (
            f"{f.name}: 'Left open at the end' card heading not found"
        )


def test_left_open_docs_mention_the_new_card():
    """AC6: README's 'What the site shows' section tells the reader what the sprint page now shows."""
    readme = (REPO_ROOT / "README.md").read_text()
    # README's 'What the site shows' section mentions the left-open card
    what_shows = readme[readme.index("## What the site shows"):]
    assert "still open" in what_shows, (
        "README's 'What the site shows' section should mention what was still open"
    )
    assert "waiting, blocked" in what_shows, (
        "README should mention the three states: waiting, blocked or refused"
    )
    assert "refused" in what_shows, (
        "README should mention the three states: waiting, blocked or refused"
    )


def test_readme_sprint_overview_mentions_stories_under_epics():
    """AC9: README's 'What the site shows' section says
    the sprint page lists the sprint's stories story by story, grouped under
    their epics, each epic's heading showing how many of its stories are done,
    and each story carrying its status, a line of what happened to it and its
    time."""
    readme = (REPO_ROOT / "README.md").read_text()
    what_shows = readme[readme.index("## What the site shows"):]
    assert "story by story" in what_shows, (
        "README's 'What the site shows' section should say stories story by story"
    )
    assert "grouped under their" in what_shows and "epic" in what_shows, (
        "README should say the stories are grouped under their epics"
    )
    assert "done count" in what_shows, (
        "README should say each epic's heading shows how many of its stories are done"
    )
    assert "what happened to it and its time" in what_shows, (
        "README should say each story carries what happened to it and its time"
    )


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
    assert "Landed first try" in source, (
        "AC1: no assertion on the 'Landed first try' label"
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
