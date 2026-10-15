"""Browser tests: load pages from build/ and verify sprint navigation structure."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
PACKAGE_DIR = REPO_ROOT / ".package"
DELIVERY_HISTORY_TAG = REPO_ROOT / "delivery-history.tag"




def _package_dir() -> Path:
    """Locate the package directory under ./.package/ named by delivery-history.tag."""
    tag = DELIVERY_HISTORY_TAG.read_text().strip()
    d = PACKAGE_DIR / tag
    assert d.is_dir(), f"package directory not found: {d}"
    return d


def _build() -> None:
    """Run the build and assert it succeeds."""
    result = subprocess.run(
        [sys.executable, "build.py"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"build failed:\n{result.stdout}\n{result.stderr}"


def _make_fake_package(tag: str, sprint_names: list[str]) -> Path:
    """Create a minimal fake package directory with the given sprint names."""
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)
    sprints = [
        {"name": n, "start": "2026-01-01", "end": "2026-01-14"} for n in sprint_names
    ]
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
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps({"sprints": sprints, "cards": []})
    )
    return pkg_dir


def _sprint_nav(html: str) -> str:
    """Extract the first <nav> element's inner HTML from a page."""
    match = re.search(r"<nav[^>]*>(.*?)</nav>", html, re.DOTALL)
    assert match, "no <nav> element found"
    return match.group(1)


def _nav_links(nav_html: str) -> list[str]:
    """Text content of all <a> elements in a nav fragment, in document order."""
    return re.findall(r"<a[^>]*>([^<]*)</a>", nav_html)


def _nav_aria_current_links(nav_html: str) -> list[str]:
    """Text of <a> elements carrying aria-current="page" in a nav fragment."""
    return re.findall(r'<a[^>]*aria-current="page"[^>]*>([^<]*)</a>', nav_html)


def test_sprint_files_and_nav_strip():
    """AC1: three sprints produce three files, each with a nav of three links in order."""
    tag = "delivery-history-TEST"
    names = ["Sprint 6", "Sprint 7", "Sprint 8"]
    _make_fake_package(tag, names)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        expected_files = [n.lower().replace(" ", "-") + ".html" for n in names]
        for f in expected_files:
            assert (BUILD_DIR / f).is_file(), f"missing {f}"
        html_files = [
            f.name for f in BUILD_DIR.iterdir() if f.suffix == ".html"
        ]
        sprint_files = [f for f in html_files if f not in ("replay.html", "story-journey.html")]
        assert sorted(sprint_files) == sorted(expected_files), (
            f"unexpected sprint files: {sprint_files}"
        )
        for f in expected_files:
            html = (BUILD_DIR / f).read_text()
            nav = _sprint_nav(html)
            assert _nav_links(nav) == names, (
                f"nav links in {f} are {_nav_links(nav)}, expected {names}"
            )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_aria_current_on_sprint_page():
    """AC2: the current sprint's link has aria-current='page'; no other link does."""
    tag = "delivery-history-TEST"
    names = ["Sprint 6", "Sprint 7", "Sprint 8"]
    _make_fake_package(tag, names)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        for name in names:
            filename = name.lower().replace(" ", "-") + ".html"
            html = (BUILD_DIR / filename).read_text()
            nav = _sprint_nav(html)
            current = _nav_aria_current_links(nav)
            assert current == [name], (
                f"{filename}: aria-current links are {current}, expected [{name!r}]"
            )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_single_sprint_nav():
    """AC3: one sprint produces one file with one link carrying aria-current='page'."""
    tag = "delivery-history-TEST"
    names = ["Sprint 1"]
    _make_fake_package(tag, names)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        filename = "sprint-1.html"
        assert (BUILD_DIR / filename).is_file(), "sprint-1.html not in build output"
        html_files = [f.name for f in BUILD_DIR.iterdir() if f.suffix == ".html"]
        sprint_files = [f for f in html_files if f not in ("replay.html", "story-journey.html")]
        assert sprint_files == [filename], f"unexpected sprint files: {sprint_files}"
        html = (BUILD_DIR / filename).read_text()
        nav = _sprint_nav(html)
        assert _nav_links(nav) == ["Sprint 1"]
        assert _nav_aria_current_links(nav) == ["Sprint 1"]
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_title_and_two_navs():
    """AC4: title contains sprint name; two distinct navs: sprint nav first, view nav second."""
    tag = "delivery-history-TEST"
    names = ["Sprint 6", "Sprint 7", "Sprint 8"]
    _make_fake_package(tag, names)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        title_match = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
        assert title_match, "no <title> element"
        assert "Sprint 7" in title_match.group(1), (
            f"title is {title_match.group(1)!r}, expected to contain 'Sprint 7'"
        )
        navs = re.findall(r"<nav[^>]*>(.*?)</nav>", html, re.DOTALL)
        assert len(navs) >= 2, f"expected at least 2 navs, found {len(navs)}"
        sprint_nav_links = _nav_links(navs[0])
        for name in names:
            assert name in sprint_nav_links, (
                f"'{name}' not in first nav links: {sprint_nav_links}"
            )
        view_nav_links = _nav_links(navs[1])
        assert "A story's journey" in view_nav_links, (
            f"'A story's journey' not in second nav links: {view_nav_links}"
        )
        first_pos = html.find("<nav")
        second_pos = html.find("<nav", first_pos + 4)
        assert second_pos > first_pos, "second nav not found after first"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_nav_hrefs_resolve():
    """AC5: every <a> in the sprint nav has a href that resolves to an existing file."""
    tag = "delivery-history-TEST"
    names = ["Sprint 6", "Sprint 7", "Sprint 8"]
    _make_fake_package(tag, names)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        for name in names:
            filename = name.lower().replace(" ", "-") + ".html"
            html = (BUILD_DIR / filename).read_text()
            nav = _sprint_nav(html)
            hrefs = re.findall(r'<a[^>]*href="([^"]*)"', nav)
            assert len(hrefs) == len(names), (
                f"{filename}: expected {len(names)} hrefs, got {len(hrefs)}"
            )
            for href in hrefs:
                target = BUILD_DIR / href
                assert target.is_file(), (
                    f"href '{href}' in {filename} does not resolve to an existing file"
                )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)
