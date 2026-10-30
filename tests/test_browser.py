"""Browser tests: load pages from build/ and verify sprint navigation structure."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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


def _make_fake_package(
    tag: str,
    sprint_names: list[str] | None = None,
    metrics: dict | None = None,
    sprints: list[dict] | None = None,
    schema_version: str = "1.0.0",
) -> Path:
    """Create a minimal fake package directory with the given sprint names."""
    if sprints is None:
        if sprint_names is None:
            sprint_names = ["Sprint 6"]
        sprints = [
            {"name": n, "start": "2026-09-22", "end": "2026-09-29"}
            for n in sprint_names
        ]
    if metrics is None:
        names = [s["name"] for s in sprints]
        metrics = {
            name: {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
            for name in names
        }
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "package": "delivery-history",
                "date": "2026-01-01",
            }
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
        json.dumps(
            {
                "sprints": sprints,
                "cards": [],
                "crew_repository": "mqucifer/crew",
                "sprint_metrics": {"answers": metrics},
            }
        )
    )
    return pkg_dir


def _sprint_nav(html: str) -> str:
    """Extract the sprint nav's inner HTML from a page (by aria-label)."""
    match = re.search(
        r'<nav[^>]*aria-label="Sprints"[^>]*>(.*?)</nav>', html, re.DOTALL
    )
    assert match, "no sprint nav (aria-label='Sprints') found"
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
            links = _nav_links(nav)
            assert len(links) == len(names), (
                f"nav in {f} has {len(links)} links, expected {len(names)}"
            )
            for i, name in enumerate(names):
                assert name in links[i], (
                    f"'{name}' not in link {i} of {f}: {links[i]!r}"
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
            assert len(current) == 1, (
                f"{filename}: expected 1 aria-current link, got {len(current)}: {current}"
            )
            assert name in current[0], (
                f"{filename}: aria-current link {current[0]!r} does not contain {name!r}"
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
        links = _nav_links(nav)
        assert len(links) == 1, f"expected 1 link, got {len(links)}: {links}"
        assert "Sprint 1" in links[0], f"link {links[0]!r} does not contain 'Sprint 1'"
        current = _nav_aria_current_links(nav)
        assert len(current) == 1, f"expected 1 aria-current link, got {len(current)}"
        assert "Sprint 1" in current[0], (
            f"aria-current link {current[0]!r} does not contain 'Sprint 1'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_title_and_two_navs():
    """AC4: title contains sprint name; view nav first, sprint nav second in document order."""
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
        # View nav (in header) comes before sprint nav (in content)
        view_nav = _view_nav(html)
        view_links = _nav_links(view_nav)
        assert "Sprint" in view_links, f"view nav links: {view_links}"
        assert "A story's journey" in view_links, (
            f"'A story's journey' not in view nav: {view_links}"
        )
        sprint_nav = _sprint_nav(html)
        sprint_links = _nav_links(sprint_nav)
        for name in names:
            assert any(name in link for link in sprint_links), (
                f"'{name}' not found in any sprint nav link: {sprint_links}"
            )
        # Document order: view nav before sprint nav
        view_pos = html.find('aria-label="Views"')
        sprint_pos = html.find('aria-label="Sprints"')
        assert view_pos < sprint_pos, (
            "view nav should appear before sprint nav in document order"
        )
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


def test_sprint_nav_shows_start_date():
    """AC1: each sprint nav link includes the sprint's start date alongside its name."""
    sprints = [
        {"name": "Sprint 6", "start": "2026-09-22", "end": "2026-09-29"},
        {"name": "Sprint 7", "start": "2026-09-29", "end": "2026-10-05"},
    ]
    tag = "delivery-history-TEST"
    _make_fake_package(tag, sprints=sprints)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        nav = _sprint_nav(html)
        links = _nav_links(nav)
        assert len(links) == 2, f"expected 2 links, got {len(links)}: {links}"
        # First link: Sprint 6 with start 2026-09-22
        assert "Sprint 6" in links[0], f"link 0 {links[0]!r} missing 'Sprint 6'"
        assert "2026-09-22" in links[0], f"link 0 {links[0]!r} missing '2026-09-22'"
        # Second link: Sprint 7 with start 2026-09-29
        assert "Sprint 7" in links[1], f"link 1 {links[1]!r} missing 'Sprint 7'"
        assert "2026-09-29" in links[1], f"link 1 {links[1]!r} missing '2026-09-29'"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_nav_chronological_order_preserved():
    """AC2: non-sequential sprint names preserve document order with dates visible."""
    sprints = [
        {"name": "Sprint 35", "start": "2026-10-24", "end": "2026-10-24"},
        {"name": "Sprint 15", "start": "2026-10-25", "end": "2026-10-25"},
    ]
    tag = "delivery-history-TEST"
    _make_fake_package(tag, sprints=sprints)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-35.html").read_text()
        nav = _sprint_nav(html)
        links = _nav_links(nav)
        assert len(links) == 2, f"expected 2 links, got {len(links)}: {links}"
        # First link: Sprint 35 with start 2026-10-24
        assert "Sprint 35" in links[0], f"link 0 {links[0]!r} missing 'Sprint 35'"
        assert "2026-10-24" in links[0], f"link 0 {links[0]!r} missing '2026-10-24'"
        # Second link: Sprint 15 with start 2026-10-25
        assert "Sprint 15" in links[1], f"link 1 {links[1]!r} missing 'Sprint 15'"
        assert "2026-10-25" in links[1], f"link 1 {links[1]!r} missing '2026-10-25'"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _view_nav(html: str) -> str:
    """Extract the view nav's inner HTML from a page (by aria-label)."""
    match = re.search(
        r'<nav[^>]*aria-label="Views"[^>]*>(.*?)</nav>', html, re.DOTALL
    )
    assert match, "no view nav (aria-label='Views') found"
    return match.group(1)


def test_sprint_overview_header_and_stats():
    """AC1: h1 contains sprint name, header has dates, stats show the right values."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_minutes": 102,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # h1 contains the sprint name
        h1_match = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL)
        assert h1_match, "no <h1> element found"
        assert "Sprint 6" in h1_match.group(1), (
            f"h1 is {h1_match.group(1)!r}, expected to contain 'Sprint 6'"
        )
        # header area contains the dates
        assert "2026-09-22" in html, "start date not in page"
        assert "2026-09-29" in html, "end date not in page"
        # stats section contains the expected values
        stats = _stats_section(html)
        assert "22" in stats, f"throughput '22' not in stats: {stats[:200]}"
        assert "63" in stats, f"points '63' not in stats: {stats[:200]}"
        assert "12 of 22" in stats, f"'12 of 22' not in stats: {stats[:200]}"
        assert ">1<" in stats or " 1 " in stats, (
            f"escalation '1' not in stats: {stats[:200]}"
        )
        assert "1 hr 42 min" in stats, f"'1 hr 42 min' not in stats: {stats[:200]}"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_stat_value_css_properties():
    """AC2: .stat__value uses var(--font-sans), 700, -0.01em, tabular-nums."""
    css = (REPO_ROOT / "site" / "css" / "site.css").read_text()
    # Find the .stat__value rule
    match = re.search(
        r"\.stat__value\s*\{([^}]+)\}", css, re.DOTALL
    )
    assert match, ".stat__value rule not found in site.css"
    rule = match.group(1)
    assert "var(--font-sans)" in rule, (
        f".stat__value font-family should be var(--font-sans): {rule}"
    )
    assert "700" in rule, f".stat__value font-weight should be 700: {rule}"
    assert "-0.01em" in rule, f".stat__value letter-spacing should be -0.01em: {rule}"
    assert "tabular-nums" in rule, (
        f".stat__value font-variant-numeric should be tabular-nums: {rule}"
    )


def test_zero_escalation_renders_zero():
    """AC3: escalation_count 0 renders '0', not 'N/A' or empty."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        stats = _stats_section(html)
        # Find the escalations stat
        esc_match = re.search(
            r'<span class="stat__value[^"]*">([^<]*?)</span>\s*<span class="stat__label">escalations</span>',
            stats,
            re.DOTALL,
        )
        assert esc_match, "escalations stat not found in stats section"
        value = esc_match.group(1).strip()
        assert value == "0", (
            f"escalation stat is {value!r}, expected '0'"
        )
        assert "N/A" not in value
        assert value != ""
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_no_raw_hex_in_inline_styles():
    """AC4: no raw hex colour in the rendered page's inline styles."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_days": 3.2,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # Find all style attributes and check for hex colours
        style_attrs = re.findall(r'style="([^"]*)"', html)
        for style in style_attrs:
            hex_match = re.search(r"#[0-9A-Fa-f]{3,8}\b", style)
            assert not hex_match, (
                f"raw hex colour in inline style: '{style}' (found {hex_match.group(0)})"
            )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_header_meta_line_and_document_order():
    """AC5: header meta line is 'mqucifer / crew · sprint-metrics', dates before stats."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_days": 3.2,
            }
        },
        sprints=[{"name": "Sprint 6", "start": "2026-09-22", "end": "2026-09-29"}],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # Meta line
        assert "mqucifer / crew · sprint-metrics" in html, (
            "meta line 'mqucifer / crew · sprint-metrics' not found in header"
        )
        # h1 contains sprint name
        h1_match = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL)
        assert h1_match and "Sprint 6" in h1_match.group(1)
        # Dates appear before the stats section in document order
        date_pos = html.find("2026-09-22")
        stats_pos = html.find('class="stats"')
        assert date_pos != -1, "start date not found"
        assert stats_pos != -1, "stats section not found"
        assert date_pos < stats_pos, (
            f"dates (pos {date_pos}) should appear before stats (pos {stats_pos})"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_view_nav_aria_current():
    """AC6: view nav has three links in order; Sprint has aria-current=page, others don't."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 1,
                "points_delivered": 3,
                "first_attempt_numerator": 1,
                "first_attempt_denominator": 1,
                "escalation_count": 0,
                "cycle_time_days": 1.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        view_nav = _view_nav(html)
        # Three links in order
        links = re.findall(r"<a[^>]*>(.*?)</a>", view_nav)
        assert links == ["Sprint", "A story's journey", "Replay"], (
            f"view nav links are {links}, expected ['Sprint', \"A story's journey\", 'Replay']"
        )
        # Sprint link has aria-current="page"
        sprint_link = re.search(
            r'<a[^>]*aria-current="page"[^>]*>Sprint</a>', view_nav
        )
        assert sprint_link, "Sprint link does not have aria-current='page'"
        # Other links do NOT have aria-current
        for text in ("A story's journey", "Replay"):
            link_match = re.search(
                rf'<a[^>]*>{re.escape(text)}</a>', view_nav
            )
            assert link_match, f"link for {text!r} not found"
            assert "aria-current" not in link_match.group(0), (
                f"link {text!r} should not have aria-current"
            )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cycle_time_is_fourth_stat():
    """AC7: '1 hr 42 min' is the fourth stat, label 'cycle time', after throughput/first-attempt/escalation."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_minutes": 102,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        stats = _stats_section(html)
        # Extract all stat values in order
        values = re.findall(
            r'<span class="stat__value[^"]*">(.*?)</span>', stats, re.DOTALL
        )
        labels = re.findall(
            r'<span class="stat__label">(.*?)</span>', stats, re.DOTALL
        )
        # The fourth stat (index 3) should be cycle time
        assert len(values) >= 4, f"expected at least 4 stats, got {len(values)}"
        assert values[3].strip() == "1 hr 42 min", (
            f"4th stat value is {values[3]!r}, expected '1 hr 42 min'"
        )
        assert labels[3].strip() == "cycle time", (
            f"4th stat label is {labels[3].strip()!r}, expected 'cycle time'"
        )
        # Verify the three stats before it
        assert "22" in values[0], f"1st stat is {values[0]!r}, expected throughput"
        assert "12 of 22" in values[1], (
            f"2nd stat is {values[1]!r}, expected first-attempt"
        )
        assert values[2].strip() == "1", (
            f"3rd stat is {values[2]!r}, expected escalation '1'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _stats_section(html: str) -> str:
    """Extract the stats section's inner HTML from a page (by class)."""
    match = re.search(
        r'<section class="stats"[^>]*>(.*?)</section>', html, re.DOTALL
    )
    assert match, "no stats section (class='stats') found"
    return match.group(1)


def test_dark_theme_background_and_text_tokens():
    """AC4: under data-theme='dark', page bg resolves to espresso and stat text to light-on-dark."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_days": 3.2,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        design_system_version = (
            REPO_ROOT / "site" / "css" / "design-system.version"
        ).read_text().strip()
        css_path = PACKAGE_DIR / f"design-system-{design_system_version}.css"
        assert css_path.is_file(), f"design-system CSS not found: {css_path}"

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()

            def handle_route(route):
                route.fulfill(
                    status=200,
                    content_type="text/css",
                    body=css_path.read_bytes(),
                )

            page.route(
                "**/cdn.jsdelivr.net/gh/mqucifer/design-system*/styles.css",
                handle_route,
            )

            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stat__value")

            # Switch to dark theme
            page.evaluate(
                "document.documentElement.setAttribute('data-theme', 'dark')"
            )
            page.wait_for_timeout(100)

            # Page background should resolve to espresso #1C1510
            bg = page.evaluate(
                "getComputedStyle(document.body).backgroundColor"
            )
            assert bg == "rgb(28, 21, 16)", (
                f"dark-theme page background is {bg!r}, "
                f"expected rgb(28, 21, 16) (espresso / --color-bg)"
            )

            # Stat text should resolve to light-on-dark #F3E9DA
            stat_color = page.evaluate(
                "getComputedStyle(document.querySelector('.stat__value')).color"
            )
            assert stat_color == "rgb(243, 233, 218)", (
                f"dark-theme stat text color is {stat_color!r}, "
                f"expected rgb(243, 233, 218) (--color-text)"
            )

            # No raw hex colour in inline styles (final clause of AC4)
            style_attrs = page.evaluate(
                """
                () => Array.from(document.querySelectorAll('[style]'))
                         .map(el => el.getAttribute('style'))
                """
            )
            for style in style_attrs:
                hex_match = re.search(r"#[0-9A-Fa-f]{3,8}\b", style)
                assert not hex_match, (
                    f"raw hex colour in inline style: '{style}' "
                    f"(found {hex_match.group(0)})"
                )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _make_package_with_stories(
    tag: str,
    stories: list[dict],
    cards: list[dict],
    sprint_names: list[str] | None = None,
) -> Path:
    """Create a fake package with analysis.stories and cards populated."""
    if sprint_names is None:
        sprint_names = ["Sprint 6"]
    sprints = [
        {"name": n, "start": "2026-09-22", "end": "2026-09-29"}
        for n in sprint_names
    ]
    first_try_count = sum(
        1 for s in stories if s.get("delivered") and len(s.get("blocks", [])) == 1
    )
    metrics = {
        name: {
            "throughput": len(stories),
            "points_delivered": 10,
            "first_attempt_numerator": first_try_count,
            "first_attempt_denominator": max(len(stories), 1),
            "escalation_count": 0,
            "cycle_time_days": 2.0,
        }
        for name in sprint_names
    }
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
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps(
            {
                "sprints": sprints,
                "cards": cards,
                "crew_repository": "mqucifer/crew",
                "sprint_metrics": {"answers": metrics},
                "analysis": {"stories": stories},
            }
        )
    )
    return pkg_dir


def test_attempt_row_refused_landed_merged():
    """AC1: a delivered story with 4 refused + 1 landed blocks renders 4 stage-1 and 1 done blocks, status 'merged'."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 125, "repo": "mqucifer/crew"},
                "blocks": ["refused", "refused", "refused", "refused", "landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 125,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "card.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # The row for #125 exists
        assert "#125" in html, "card number #125 not found in page"
        # Exactly four refused blocks
        refused_count = html.count('class="attempt-block attempt-block--refused"')
        assert refused_count == 4, f"expected 4 refused blocks, got {refused_count}"
        # Exactly one landed block
        landed_count = html.count('class="attempt-block attempt-block--landed"')
        assert landed_count == 1, f"expected 1 landed block, got {landed_count}"
        # Status label reads 'merged'
        assert 'class="attempt-status attempt-status--merged"' in html, (
            "merged status class not found"
        )
        assert ">merged<" in html, "status text 'merged' not found"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_mixed_blocks_in_order():
    """AC2: row for #127 has seven blocks in the exact order: refused, refused, blocked, crew_fix, refused, crew_fix, landed."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 127, "repo": "mqucifer/crew"},
                "blocks": [
                    "refused",
                    "refused",
                    "blocked",
                    "crew_fix",
                    "refused",
                    "crew_fix",
                    "landed",
                ],
                "crew_fixes": [
                    {"number": 141, "repo": "mqucifer/crew"},
                    {"number": 144, "repo": "mqucifer/crew"},
                ],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 127,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "thresholds.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        assert "#127" in html, "card number #127 not found"
        # Extract the blocks div for this row
        blocks_match = re.search(
            r"#127.*?<div class=\"blocks\">(.*?)</div>",
            html,
            re.DOTALL,
        )
        assert blocks_match, "blocks div for #127 not found"
        blocks_html = blocks_match.group(1)
        # Verify the order of block classes
        expected = [
            "attempt-block--refused",
            "attempt-block--refused",
            "attempt-block--blocked",
            "attempt-block--crew-fix",
            "attempt-block--refused",
            "attempt-block--crew-fix",
            "attempt-block--landed",
        ]
        positions = []
        search_from = 0
        for cls in expected:
            pos = blocks_html.find(cls, search_from)
            assert pos >= 0, f"block {cls} not found or out of order"
            positions.append(pos)
            search_from = pos + len(cls)
        assert len(positions) == 7, f"expected 7 block positions, got {len(positions)}"
        # Status is merged
        assert 'class="attempt-status attempt-status--merged"' in html
        assert ">merged<" in html
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_legend_exactly_four_items():
    """AC3: the legend contains exactly four items in the required order."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 125, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 125,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "x",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # Extract the legend
        legend_match = re.search(
            r'<div class="attempt-legend">(.*?)</div>',
            html,
            re.DOTALL,
        )
        assert legend_match, "attempt-legend div not found"
        legend_html = legend_match.group(1)
        # Check the four items in order
        expected_labels = [
            "attempt that landed",
            "refused, repaired",
            "blocked",
            "crew fix merged",
        ]
        for label in expected_labels:
            assert label in legend_html, f"legend item {label!r} not found"
        # Verify order
        positions = [legend_html.index(label) for label in expected_labels]
        assert positions == sorted(positions), f"legend items out of order: {positions}"
        # Exactly four items (count the swatch elements)
        swatch_count = legend_html.count('class="swatch')
        assert swatch_count == 4, f"expected 4 legend swatches, got {swatch_count}"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_empty_blocks_in_progress():
    """AC4: a delivered story with empty blocks shows a single dashed-border block and its pattern as status."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 199, "repo": "mqucifer/crew"},
                "blocks": [],
                "crew_fixes": [],
                "delivered": True,
                "pattern": "first_try",
            }
        ],
        cards=[
            {
                "number": 199,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "pending.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        assert "#199" in html, "card number #199 not found"
        # Single dashed-border block (crew-fix class)
        crew_fix_count = html.count('class="attempt-block attempt-block--crew-fix"')
        assert crew_fix_count == 1, f"expected 1 crew-fix block, got {crew_fix_count}"
        # No other block types
        assert 'attempt-block--refused' not in html
        assert 'attempt-block--landed' not in html
        assert 'attempt-block--blocked' not in html
        # Status is 'first try' with the first-try class
        assert 'class="attempt-status attempt-status--first-try"' in html, (
            "first-try status class not found"
        )
        assert ">first try<" in html, "status text 'first try' not found"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_site_css_no_placeholder_and_striped_gradient():
    """AC5: site.css has no 'crew:placeholder' and contains a repeating-linear-gradient with the blocked-tone variables."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[],
        cards=[],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        css = (BUILD_DIR / "css" / "site.css").read_text()
        # No placeholder marker
        assert "crew:placeholder" not in css, "crew:placeholder still in site.css"
        # Striped-blocked background uses repeating-linear-gradient with both tone variables
        blocked_match = re.search(
            r"repeating-linear-gradient.*--tone-blocked-text.*--tone-blocked-bg",
            css,
            re.DOTALL,
        )
        assert blocked_match, (
            "no repeating-linear-gradient with tone-blocked-text and tone-blocked-bg found"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_chart_row_count_and_order():
    """AC6: 5 stories produce exactly 5 attempt rows, each with '#<number>' and .num class, in package order."""
    tag = "delivery-history-TEST"
    story_numbers = [101, 102, 103, 104, 105]
    stories = [
        {
            "card": {"number": n, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        }
        for n in story_numbers
    ]
    cards = [
        {
            "number": n,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": f"story-{n}.py",
        }
        for n in story_numbers
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # Exactly 5 attempt rows
        row_count = html.count('class="attempt-row"')
        assert row_count == 5, f"expected 5 attempt rows, got {row_count}"
        # Each row has a .num class with the card number
        for n in story_numbers:
            assert f'class="num meta">#{n}<' in html, f"card #{n} with .num class not found"
        # Rows appear in the same order as the stories list
        positions = [html.index(f">#{n}<") for n in story_numbers]
        assert positions == sorted(positions), (
            f"rows out of order: positions {positions} for numbers {story_numbers}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_legend_exact_dom_order_no_fifth():
    """AC7: legend items in exact DOM order, no fifth item present."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 1, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 1,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "x",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        legend_match = re.search(
            r'<div class="attempt-legend">(.*?)</div>',
            html,
            re.DOTALL,
        )
        assert legend_match, "attempt-legend not found"
        legend_html = legend_match.group(1)
        # Exactly four <span> items
        span_count = len(re.findall(r"<span>", legend_html))
        assert span_count == 4, f"expected 4 legend spans, got {span_count}"
        # Check exact order by position
        expected = [
            "attempt that landed",
            "refused, repaired",
            "blocked",
            "crew fix merged",
        ]
        for i, label in enumerate(expected):
            pos = legend_html.index(label)
            if i > 0:
                prev_pos = legend_html.index(expected[i - 1])
                assert pos > prev_pos, f"legend item {i} out of order"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_block_counts_per_story():
    """AC8: #125 has exactly 5 blocks, #128 has exactly 1 block using tone-done-text (not stage-1)."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 125, "repo": "mqucifer/crew"},
            "blocks": ["refused", "refused", "refused", "refused", "landed"],
            "crew_fixes": [],
            "delivered": True,
        },
        {
            "card": {"number": 128, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        },
    ]
    cards = [
        {
            "number": 125,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "card.py",
        },
        {
            "number": 128,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "report.py",
        },
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # Extract blocks for #125
        blocks_125_match = re.search(
            r"#125.*?<div class=\"blocks\">(.*?)</div>",
            html,
            re.DOTALL,
        )
        assert blocks_125_match, "blocks div for #125 not found"
        blocks_125 = blocks_125_match.group(1)
        block_count_125 = len(re.findall(r'<span class="attempt-block ', blocks_125))
        assert block_count_125 == 5, f"#125: expected 5 blocks, got {block_count_125}"

        # Extract blocks for #128
        blocks_128_match = re.search(
            r"#128.*?<div class=\"blocks\">(.*?)</div>",
            html,
            re.DOTALL,
        )
        assert blocks_128_match, "blocks div for #128 not found"
        blocks_128 = blocks_128_match.group(1)
        block_count_128 = len(re.findall(r'<span class="attempt-block ', blocks_128))
        assert block_count_128 == 1, f"#128: expected 1 block, got {block_count_128}"
        # The single block is landed (tone-done-text), not refused (stage-1)
        assert "attempt-block--landed" in blocks_128, "#128 block should be landed"
        assert "attempt-block--refused" not in blocks_128, (
            "#128 block should not be refused/stage-1"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_chart_heading_text_and_style():
    """AC9: heading text is exact and CSS sets Fraunces at --text-xl for the chart heading."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 1, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 1,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "x",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # Exact heading text
        assert "The Architect's split, story by story" in html, (
            "heading text not found"
        )
        # The heading is an h2 with id split-h
        h2_match = re.search(
            r'<h2 id="split-h">(.*?)</h2>',
            html,
            re.DOTALL,
        )
        assert h2_match, "h2#split-h not found"
        assert h2_match.group(1).strip() == "The Architect's split, story by story"
        # CSS sets the font and size for this heading
        css = (BUILD_DIR / "css" / "site.css").read_text()
        # The .sprint-chart .card__head h2 rule (or equivalent) uses the display font and xl size
        assert "--font-display" in css, "var(--font-display) not in site.css"
        assert "--text-xl" in css, "var(--text-xl) not in site.css"
        # Check the rule targets the chart heading
        heading_rule = re.search(
            r"\.sprint-chart\s+\.card__head\s+h2\s*{[^}]*}",
            css,
        )
        assert heading_rule, "no CSS rule for .sprint-chart .card__head h2"
        rule_body = heading_rule.group(0)
        assert "var(--font-display)" in rule_body, "heading rule missing font-family"
        assert "var(--text-xl)" in rule_body, "heading rule missing font-size"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _make_package_with_changed(
    tag: str,
    sprint_name: str,
    changed: list[dict],
) -> Path:
    """Create a fake package with analysis.sprints[].changed populated."""
    sprints = [{"name": sprint_name, "start": "2026-09-22", "end": "2026-09-29"}]
    metrics = {
        sprint_name: {
            "throughput": 5,
            "points_delivered": 10,
            "first_attempt_numerator": 3,
            "first_attempt_denominator": 5,
            "escalation_count": 0,
            "cycle_time_days": 2.0,
        }
    }
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
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps(
            {
                "sprints": sprints,
                "cards": [],
                "crew_repository": "mqucifer/crew",
                "sprint_metrics": {"answers": metrics},
                "analysis": {"sprints": [{"sprint": sprint_name, "changed": changed}]},
            }
        )
    )
    return pkg_dir


def test_changed_trend_single_entry_reading_order():
    """AC1, AC5: cycle_time_days renders 'cycle time' label and hours-and-minutes values."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 7",
        [
            {
                "text": "Cycle time improved",
                "measure": "cycle_time_days",
                "previous": 5.2,
                "now": 3.8,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        section_match = re.search(
            r'<section class="card changed-trend".*?</section>',
            html,
            re.DOTALL,
        )
        assert section_match, "changed-trend section not found"
        section_html = section_match.group(0)
        # AC5: label is 'cycle time', not the raw measure name
        pos_label = section_html.index("cycle time")
        assert "cycle_time_days" not in section_html, (
            "raw measure name 'cycle_time_days' appears in changed-trend section"
        )
        # AC1: values are formatted as hours and minutes
        pos_prev = section_html.index("124 hr 48 min")
        pos_now = section_html.index("91 hr 12 min")
        pos_text = section_html.index("Cycle time improved")
        assert pos_text < pos_label < pos_prev < pos_now, (
            f"reading order violated: text@{pos_text}, label@{pos_label}, "
            f"prev@{pos_prev}, now@{pos_now}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)




def test_changed_trend_empty_no_entries():
    """AC3: empty changed array produces no changed-trend entries."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(tag, "Sprint 6", [])
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        assert "changed-trend-entry" not in html, (
            "changed-trend-entry element found with empty changed array"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_heading_before_entries():
    """AC4: heading with 'changed' appears before entries, in same section."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 7",
        [
            {
                "text": "Cycle time improved",
                "measure": "cycle_time_days",
                "previous": 5.2,
                "now": 3.8,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        heading_match = re.search(
            r'<(h[23])[^>]*>(?:(?!</\1>).)*?changed(?:(?!</\1>).)*?</\1>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        assert heading_match, "no h2/h3 heading containing 'changed' found"
        heading_pos = heading_match.start()
        entry_pos = html.index("Cycle time improved")
        assert heading_pos < entry_pos, (
            f"heading at {heading_pos} should appear before entry at {entry_pos}"
        )
        section_match = re.search(
            r'<section class="card changed-trend".*?</section>',
            html,
            re.DOTALL,
        )
        assert section_match, "changed-trend section not found"
        section_start = section_match.start()
        section_end = section_match.end()
        assert section_start < heading_pos < section_end, (
            "heading not inside the changed-trend section"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_values_have_num_class():
    """AC7: previous and now values carry the 'num' class and are separated by &rarr;."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 7",
        [
            {
                "text": "Cycle time improved",
                "measure": "cycle_time_days",
                "previous": 5.2,
                "now": 3.8,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        assert 'class="num">124 hr 48 min<' in html, (
            "previous value does not have class 'num' with formatted text"
        )
        assert 'class="num">91 hr 12 min<' in html, (
            "now value does not have class 'num' with formatted text"
        )
        # AC7: the arrow between them
        values_div = re.search(
            r'class="changed-trend-values">.*?</div>', html, re.DOTALL
        )
        assert values_div, "no changed-trend-values div found"
        assert "&rarr;" in values_div.group(0), (
            "no &rarr; entity between the two values"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)




def test_failure_causes_empty_renders_no_failures():
    """AC2: empty top_failure_causes renders 'No failures recorded' with no bar elements."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_days": 3.2,
                "top_failure_causes": [],
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        assert "No failures recorded" in html, "'No failures recorded' not found"
        # No bar elements
        assert 'class="cause-bar' not in html, "bar elements found for empty causes"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_failure_causes_2_0_list_shape_renders_class_rows():
    """AC1: 2.0.0 {class, role, count} entries render one row each, the class as the
    label, each count preserved, and no row is the 'Cause not recorded' placeholder."""
    tag = "delivery-history-TEST"
    causes = [
        {"class": "VERIFY", "role": "Developer", "count": 7},
        {"class": "EDIT", "role": "Developer", "count": 1},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
        schema_version="2.0.0",
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # one row per entry
        rows = section.count('class="cause-row"')
        assert rows == 2, f"expected 2 cause rows, got {rows}"
        # the class is shown as the label, not the placeholder
        assert ">VERIFY</span>" in section, "2.0.0 class 'VERIFY' not shown as a label"
        assert ">EDIT</span>" in section, "2.0.0 class 'EDIT' not shown as a label"
        # each row's count equals the entry's count
        assert ">7</span>" in section, "VERIFY count 7 not shown"
        assert ">1</span>" in section, "EDIT count 1 not shown"
        # a class-carrying entry is not the 'Cause not recorded' placeholder
        assert "Cause not recorded" not in section, (
            "a class-carrying entry must not render as 'Cause not recorded'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_failure_causes_1x_map_shape_renders_rows():
    """AC2: a 1.x {class: count} map still renders one row per entry with those counts."""
    tag = "delivery-history-TEST"
    causes = {"VERIFY": 7, "EDIT": 1}
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # one row per entry
        rows = section.count('class="cause-row"')
        assert rows == 2, f"expected 2 cause rows, got {rows}"
        # the counts are preserved
        assert ">7</span>" in section, "VERIFY count 7 not shown"
        assert ">1</span>" in section, "EDIT count 1 not shown"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_failure_causes_2_0_empty_list_renders_no_failures():
    """AC3: a 2.0.0 package with an empty top_failure_causes list renders 'No failures
    recorded' and the build does not fail."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": [],
            }
        },
        schema_version="2.0.0",
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()  # asserts the build did not fail
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        assert "No failures recorded" in section, "'No failures recorded' not found"
        assert 'class="cause-row"' not in section, "cause rows found for empty causes"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_failure_causes_2_0_absent_renders_no_failures():
    """AC3: a 2.0.0 package with no top_failure_causes renders 'No failures recorded'
    and the build does not fail."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
        schema_version="2.0.0",
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()  # asserts the build did not fail
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        assert "No failures recorded" in section, "'No failures recorded' not found"
        assert 'class="cause-row"' not in section, "cause rows found for absent causes"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_failure_causes_bar_width_proportional():
    """AC3: bar for count 6 of max 10 has width 60% using stage-2 background."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "A test's assertion failed", "count": 10},
        {"reason": '"already exists"', "count": 6},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        assert "width:60%" in section, "bar for count 6 should be 60% width"
        # The .cause-bar class uses var(--stage-2) in site.css
        css = (BUILD_DIR / "css" / "site.css").read_text()
        assert "var(--stage-2)" in css, "stage-2 not used for cause-bar background in site.css"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_failure_causes_heading_and_row_count():
    """Section heading is 'Why work didn't land first time' with exactly 4 cause rows fed as codes."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "test_assertion_failed", "count": 10},
        {"reason": "already_exists", "count": 6},
        {"reason": "must_create_or_edit_file", "count": 3},
        {"reason": "unrecorded", "count": 2},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_days": 3.2,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        assert "Why work didn't land first time" in html, "section heading not found"
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        row_count = section.count('class="cause-row"')
        assert row_count == 4, f"expected exactly 4 cause rows, got {row_count}"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_failure_causes_unrecorded_uses_dim_and_raised():
    """AC5: 'Cause not recorded' uses dim text colour and surface-raised bar background."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "A test's assertion failed", "count": 10},
        {"reason": "Cause not recorded", "count": 2},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # The unrecorded reason span has class="meta" (dim text via design system)
        assert 'class="meta">Cause not recorded' in section, (
            "unrecorded reason should use .meta class for dim text"
        )
        # The bar uses cause-bar--unrecorded class
        assert "cause-bar--unrecorded" in section, "unrecorded bar class missing"
        # CSS maps cause-bar--unrecorded to surface-raised
        css = (BUILD_DIR / "css" / "site.css").read_text()
        assert "var(--color-surface-raised)" in css, (
            "surface-raised not used for unrecorded bar in site.css"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_failure_causes_bar_widths_and_stage2_color():
    """AC6: first bar 100%, second bar 60%, both use var(--stage-2) background."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "test_assertion_failed", "count": 10},
        {"reason": "already_exists", "count": 6},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # First bar: width:100%
        assert "width:100%" in section, "first bar should be 100% width"
        # Second bar: width:60%
        assert "width:60%" in section, "second bar should be 60% width"
        # Both bars use .cause-bar (stage-2), not --unrecorded
        normal_bars = section.count('class="cause-bar"')
        assert normal_bars == 2, f"expected 2 normal cause-bar elements, got {normal_bars}"
        assert "cause-bar--unrecorded" not in section, (
            "unrecorded class should not appear for these causes"
        )
        # CSS confirms stage-2 background
        css = (BUILD_DIR / "css" / "site.css").read_text()
        assert "var(--stage-2)" in css, "stage-2 not used for cause-bar background"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _make_package_with_decided(tag: str, decided: list[dict]) -> Path:
    """Create a fake package with analysis.sprints[0].decided populated."""
    sprints = [{"name": "Sprint 6", "start": "2026-09-22", "end": "2026-09-29"}]
    metrics = {
        "Sprint 6": {
            "throughput": 5,
            "points_delivered": 10,
            "first_attempt_numerator": 3,
            "first_attempt_denominator": 5,
            "escalation_count": 0,
            "cycle_time_days": 2.0,
        }
    }
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
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps(
            {
                "sprints": sprints,
                "cards": [],
                "crew_repository": "mqucifer/crew",
                "sprint_metrics": {"answers": metrics},
                "analysis": {
                    "sprints": [{"sprint": "Sprint 6", "decided": decided}],
                },
            }
        )
    )
    return pkg_dir


def test_feature_panel_decided_entries():
    """AC1+AC4+AC6: decided entries render with heading, times in tabular-nums, text, kind, and number."""
    tag = "delivery-history-TEST"
    decided = [
        {"at": "2026-09-25T23:37:00Z", "kind": "design_revision", "number": 122, "repo": "mqucifer/crew", "text": "Architect revised the design into seven modules"},
        {"at": "2026-09-25T23:38:00Z", "kind": "merge", "number": 123, "repo": "mqucifer/crew", "text": "crew merged the revision"},
        {"at": "2026-09-25T23:44:00Z", "kind": "split", "number": 124, "repo": "mqucifer/crew", "text": "Business Analyst split 8 stories from the new design"},
    ]
    _make_package_with_decided(tag, decided)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # Feature panel heading
        assert "Decided by the crew" in html, "feature panel heading not found"
        assert 'class="feature' in html, "feature class not found"
        # Extract the decided-list section
        section_start = html.index('class="decided-list"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # Three times in order
        pos_2337 = section.index("23:37")
        pos_2338 = section.index("23:38")
        pos_2344 = section.index("23:44")
        assert pos_2337 < pos_2338 < pos_2344, "times not in order"
        # tabular-nums via class="num"
        num_count = section.count('class="num"')
        assert num_count == 3, f"expected 3 .num spans in decided-list, got {num_count}"
        # AC1: text field values present
        assert "Architect revised the design into seven modules" in section
        assert "crew merged the revision" in section
        assert "Business Analyst split 8 stories from the new design" in section
        # AC6: kind name (underscores replaced) and card number present
        assert "design revision" in section, "kind 'design_revision' not rendered with spaces"
        assert "#122" in section, "card number #122 not found"
        assert "merged" in section, "'merged' not found in second entry"
        assert "#123" in section, "card number #123 not found"
        assert "split" in section, "'split' not found in third entry"
        assert "#124" in section, "card number #124 not found"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_feature_panel_empty_decided():
    """AC2: empty decided renders 'No decisions recorded this sprint' with no timestamped entries."""
    tag = "delivery-history-TEST"
    _make_package_with_decided(tag, [])
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        assert "No decisions recorded this sprint" in html, "empty message not found"
        assert 'class="decided-list"' not in html, "decided-list should not appear for empty decided"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_feature_panel_light_theme_colors():
    """AC3+AC5: light-theme feature panel uses feature-bg, feature-text, feature-dim tokens."""
    tag = "delivery-history-TEST"
    decided = [
        {"at": "2026-09-25T23:37:00Z", "kind": "design_revision", "number": 122, "repo": "mqucifer/crew", "text": "Architect revised the design into seven modules"},
    ]
    _make_package_with_decided(tag, decided)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        design_system_version = (
            REPO_ROOT / "site" / "css" / "design-system.version"
        ).read_text().strip()
        css_path = PACKAGE_DIR / f"design-system-{design_system_version}.css"
        assert css_path.is_file(), f"design-system CSS not found: {css_path}"

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()

            def handle_route(route):
                route.fulfill(
                    status=200,
                    content_type="text/css",
                    body=css_path.read_bytes(),
                )

            page.route(
                "**/cdn.jsdelivr.net/gh/mqucifer/design-system*/styles.css",
                handle_route,
            )

            page.goto(f"file://{page_path}")
            page.wait_for_selector(".feature")

            # Ensure light theme
            page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
            page.wait_for_timeout(100)

            # Panel background: --color-feature-bg = #2E1F14 → rgb(46, 31, 20)
            bg = page.evaluate(
                "getComputedStyle(document.querySelector('.feature')).backgroundColor"
            )
            assert bg == "rgb(46, 31, 20)", (
                f"feature panel background is {bg!r}, "
                f"expected rgb(46, 31, 20) (--color-feature-bg)"
            )

            # Heading text: --color-feature-text = #F6EFE3 → rgb(246, 239, 227)
            heading_color = page.evaluate(
                "getComputedStyle(document.querySelector('.feature h2')).color"
            )
            assert heading_color == "rgb(246, 239, 227)", (
                f"feature heading color is {heading_color!r}, "
                f"expected rgb(246, 239, 227) (--color-feature-text)"
            )

            # Timestamp text: --color-feature-dim = #E6D8C3 → rgb(230, 216, 195)
            ts_color = page.evaluate(
                "getComputedStyle(document.querySelector('.decided-list .num')).color"
            )
            assert ts_color == "rgb(230, 216, 195)", (
                f"timestamp color is {ts_color!r}, "
                f"expected rgb(230, 216, 195) (--color-feature-dim)"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _package() -> dict:
    """Read the delivery-history.json index from the current package directory."""
    pkg_dir = _package_dir()
    return json.loads((pkg_dir / "delivery-history.json").read_text())


def _intercept_design_system(page) -> None:
    """Intercept the design-system CDN URL and serve the local CSS file from ./.package/.

    Also intercepts the Google Fonts URL so the sandbox (no network) does not
    log a console error for the unreachable font fetch.
    """
    design_system_version = (
        REPO_ROOT / "site" / "css" / "design-system.version"
    ).read_text().strip()
    css_path = PACKAGE_DIR / f"design-system-{design_system_version}.css"
    assert css_path.is_file(), f"design-system CSS not found: {css_path}"

    def handle_design_system(route):
        route.fulfill(
            status=200,
            content_type="text/css",
            body=css_path.read_bytes(),
        )

    def handle_fonts(route):
        route.fulfill(
            status=200,
            content_type="text/css",
            body=b"",
        )

    page.route(
        "**/cdn.jsdelivr.net/gh/mqucifer/design-system*/styles.css",
        handle_design_system,
    )
    page.route(
        "**/fonts.googleapis.com/css2*",
        handle_fonts,
    )


def test_stat_values_match_package_data():
    """AC1: DOM stat values match package's sprint_metrics.answers; CSS served from local file."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_days": 3.2,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        pkg = _package()
        sprint_key = pkg["sprints"][0]["name"]
        answers = pkg["sprint_metrics"]["answers"][sprint_key]
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stat__value")

            # Exact text for stories delivered
            throughput_text = page.evaluate("""
                () => {
                    const labels = document.querySelectorAll('.stat__label');
                    for (const label of labels) {
                        if (label.textContent.trim() === 'stories delivered') {
                            const stat = label.closest('.stat');
                            return stat.querySelector('.stat__value').textContent.trim();
                        }
                    }
                    return null;
                }
            """)
            assert throughput_text == str(answers["throughput"]), (
                f"stories delivered shows {throughput_text!r}, "
                f"expected {answers['throughput']!r} from package"
            )

            # Exact text for landed first try
            first_attempt_text = page.evaluate("""
                () => {
                    const labels = document.querySelectorAll('.stat__label');
                    for (const label of labels) {
                        if (label.textContent.trim() === 'landed first try') {
                            const stat = label.closest('.stat');
                            return stat.querySelector('.stat__value').textContent.trim();
                        }
                    }
                    return null;
                }
            """)
            expected_fa = (
                f"{answers['first_attempt_numerator']} of "
                f"{answers['first_attempt_denominator']}"
            )
            assert first_attempt_text == expected_fa, (
                f"landed first try shows {first_attempt_text!r}, expected {expected_fa!r}"
            )

            # Design-system CSS was served from local file: the sandbox has no
            # network, so if --color-bg is set the CSS must have come from ./.package/
            color_bg = page.evaluate(
                "getComputedStyle(document.documentElement).getPropertyValue('--color-bg')"
            )
            assert color_bg.strip() != "", (
                "--color-bg not set; design-system CSS was not loaded from local file"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_rows_match_package_stories():
    """AC2: attempt chart contains exactly 7 rows with card numbers matching package in order."""
    tag = "delivery-history-TEST"
    story_numbers = [201, 202, 203, 204, 205, 206, 207]
    stories = [
        {
            "card": {"number": n, "repo": "mqucifer/crew"},
            "blocks": ["refused", "landed"],
            "crew_fixes": [],
            "delivered": True,
        }
        for n in story_numbers
    ]
    cards = [
        {
            "number": n,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": f"story-{n}.py",
        }
        for n in story_numbers
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        pkg = _package()
        expected_numbers = [s["card"]["number"] for s in pkg["analysis"]["stories"]]
        assert len(expected_numbers) == 7, (
            f"package has {len(expected_numbers)} stories, expected 7"
        )
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row")

            # Exactly 7 attempt rows
            row_count = page.locator(".attempt-row").count()
            assert row_count == 7, f"expected 7 attempt rows, got {row_count}"

            # Each row's card number matches the package in order
            row_numbers = page.evaluate("""
                () => Array.from(document.querySelectorAll('.attempt-row'))
                    .map(row => {
                        const num = row.querySelector('.num');
                        return num ? num.textContent.trim() : null;
                    })
            """)
            expected_texts = [f"#{n}" for n in expected_numbers]
            assert row_numbers == expected_texts, (
                f"row card numbers are {row_numbers}, expected {expected_texts}"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_name_in_header_and_no_console_errors():
    """AC3: single-sprint page renders without error, header shows sprint name, no JS console errors."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        pkg = _package()
        assert len(pkg["sprints"]) == 1, "expected single-sprint package"
        sprint_name = pkg["sprints"][0]["name"]
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)

            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text)
                if msg.type == "error"
                else None,
            )

            page.goto(f"file://{page_path}")
            page.wait_for_selector("h1")

            # Page rendered without error: h1 exists and has content
            h1_text = page.locator("h1").text_content()
            assert h1_text and len(h1_text.strip()) > 0, "h1 is empty; page did not render"

            # Header shows the sprint's name
            assert sprint_name in h1_text, (
                f"h1 is {h1_text!r}, expected to contain {sprint_name!r}"
            )

            # No JavaScript console errors
            assert not console_errors, (
                f"JavaScript console errors present: {console_errors}"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_css_custom_properties_resolve_light_theme():
    """AC4: CSS custom properties resolve to light-theme values; IIFE sets data-theme before paint."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            # Force light color scheme so the IIFE picks 'light'
            context = browser.new_context(color_scheme="light")
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stat__value")

            # data-theme is set by the IIFE before the stylesheet loads
            data_theme = page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            assert data_theme in ("light", "dark"), (
                f"data-theme is {data_theme!r}, expected 'light' or 'dark'"
            )
            assert data_theme == "light", (
                f"with color_scheme='light', data-theme should be 'light', got {data_theme!r}"
            )

            # CSS custom properties resolve to light-theme values
            color_bg = page.evaluate(
                "getComputedStyle(document.documentElement).getPropertyValue('--color-bg')"
            )
            # Light theme --color-bg is #F6EFE3 → rgb(246, 239, 227)
            # As a custom property, it returns the raw value: #F6EFE3
            assert color_bg.strip().lower() == "#f6efe3", (
                f"--color-bg is {color_bg.strip()!r}, expected '#F6EFE3' (light theme)"
            )

            color_text = page.evaluate(
                "getComputedStyle(document.documentElement).getPropertyValue('--color-text')"
            )
            # Light theme --color-text is #2E1F14
            assert color_text.strip().lower() == "#2e1f14", (
                f"--color-text is {color_text.strip()!r}, expected '#2E1F14' (light theme)"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_head_order_iife_before_links():
    """AC5: head contains design-system link, site CSS link, and theme IIFE before both."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        design_system_version = (
            REPO_ROOT / "site" / "css" / "design-system.version"
        ).read_text().strip()
        expected_design_system_href = (
            f"https://cdn.jsdelivr.net/gh/mqucifer/design-system@{design_system_version}/styles.css"
        )

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            # Get head children in document order
            head_children = page.evaluate("""
                () => Array.from(document.head.children).map(el => ({
                    tag: el.tagName,
                    href: el.href || el.getAttribute('href') || '',
                    hasIIFE: el.tagName === 'SCRIPT'
                        && el.textContent.includes('data-theme')
                }))
            """)

            # Find the IIFE script
            iife_positions = [
                i for i, child in enumerate(head_children)
                if child["tag"] == "SCRIPT" and child["hasIIFE"]
            ]
            assert len(iife_positions) == 1, (
                f"expected exactly 1 theme IIFE script, found {len(iife_positions)}"
            )
            iife_pos = iife_positions[0]

            # Find the design-system stylesheet link
            design_system_positions = [
                i for i, child in enumerate(head_children)
                if child["tag"] == "LINK"
                and child["href"] == expected_design_system_href
            ]
            assert len(design_system_positions) == 1, (
                f"expected exactly 1 design-system link with href "
                f"{expected_design_system_href!r}, found {len(design_system_positions)}"
            )
            ds_pos = design_system_positions[0]

            # Find the site CSS link
            site_css_positions = [
                i for i, child in enumerate(head_children)
                if child["tag"] == "LINK"
                and "site.css" in child["href"]
            ]
            assert len(site_css_positions) == 1, (
                f"expected exactly 1 site CSS link, found {len(site_css_positions)}"
            )
            site_pos = site_css_positions[0]

            # IIFE appears before both links in document order
            assert iife_pos < ds_pos, (
                f"theme IIFE at position {iife_pos} should be before "
                f"design-system link at position {ds_pos}"
            )
            assert iife_pos < site_pos, (
                f"theme IIFE at position {iife_pos} should be before "
                f"site CSS link at position {site_pos}"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_exactly_one_feature_one_stats_no_placeholder():
    """AC6: exactly one .feature, one .stats, zero crew:placeholder in the DOM."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stats")

            # Exactly one .feature element
            feature_count = page.locator(".feature").count()
            assert feature_count == 1, (
                f"expected exactly 1 .feature element, got {feature_count}"
            )

            # Exactly one .stats element
            stats_count = page.locator(".stats").count()
            assert stats_count == 1, (
                f"expected exactly 1 .stats element, got {stats_count}"
            )

            # Zero elements with 'crew:placeholder' text
            placeholder_count = page.locator("text=crew:placeholder").count()
            assert placeholder_count == 0, (
                f"expected 0 elements with 'crew:placeholder' text, got {placeholder_count}"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_data_theme_set_and_body_background_matches_token():
    """AC7: no console errors, data-theme set on html, body background matches --color-bg."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(color_scheme="light")
            page = context.new_page()
            _intercept_design_system(page)

            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text)
                if msg.type == "error"
                else None,
            )

            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stat__value")

            # No JavaScript console errors
            assert not console_errors, (
                f"JavaScript console errors present: {console_errors}"
            )

            # <html> has data-theme set to 'light' or 'dark'
            data_theme = page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            assert data_theme in ("light", "dark"), (
                f"data-theme is {data_theme!r}, expected 'light' or 'dark'"
            )

            # Body's computed background matches --color-bg for the active theme
            body_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
            if data_theme == "light":
                expected_bg = "rgb(246, 239, 227)"  # #F6EFE3
            else:
                expected_bg = "rgb(28, 21, 16)"  # #1C1510
            assert body_bg == expected_bg, (
                f"body background is {body_bg!r}, expected {expected_bg!r} "
                f"for theme {data_theme!r}"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_viewport_meta_in_head():
    """AC1: built sprint page <head> contains the viewport meta tag."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        head_match = re.search(r"<head>(.*?)</head>", html, re.DOTALL)
        assert head_match, "no <head> element found in built page"
        head = head_match.group(1)
        assert 'name="viewport"' in head and (
            'content="width=device-width, initial-scale=1"' in head
        ), (
            "built sprint page <head> does not contain "
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_page_scrollwidth_at_phone_width():
    """AC2: sprint page at 390px viewport has documentElement.scrollWidth <= 390."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            assert scroll_width <= 390, (
                f"sprint page scrollWidth is {scroll_width}, expected <= 390"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_story_journey_scrollwidth_at_phone_width():
    """AC1-AC2: story-journey page at 375px viewport has scrollWidth <= 375 with long titles."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    pkg_dir = PACKAGE_DIR / tag
    data = json.loads((pkg_dir / "delivery-history.json").read_text())
    data["cards"] = [
        {"repo": "mqucifer/crew", "number": 1, "title": "Fix typo"},
        {
            "repo": "mqucifer/crew",
            "number": 127,
            "title": "Extract the threshold logic into a separate module with proper type annotations and full docstrings",
        },
    ]
    (pkg_dir / "delivery-history.json").write_text(json.dumps(data))
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "story-journey.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            assert scroll_width <= 375, (
                f"story-journey page scrollWidth is {scroll_width}, expected <= 375"
            )

            # AC2: the section contains exactly 2 li elements with correct link text
            li_texts = page.eval_on_selector_all(
                "section ul li a", "els => els.map(el => el.textContent)"
            )
            assert len(li_texts) == 2, f"expected 2 li elements, found {len(li_texts)}"
            assert li_texts[0] == "mqucifer/crew#1 — Fix typo", (
                f"first link text is {li_texts[0]!r}, expected 'mqucifer/crew#1 — Fix typo'"
            )
            assert (
                li_texts[1]
                == "mqucifer/crew#127 — Extract the threshold logic into a separate module with proper type annotations and full docstrings"
            ), (
                f"second link text is {li_texts[1]!r}, expected full long title"
            )

            # A card title containing a very long unbreakable segment (no spaces)
            # must not force horizontal scroll: overflow-wrap: break-word breaks it.
            unbreakable = "a" * 200
            data["cards"] = [
                {
                    "repo": "mqucifer/crew",
                    "number": 999,
                    "title": unbreakable,
                },
            ]
            (pkg_dir / "delivery-history.json").write_text(json.dumps(data))
            _build()
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            assert scroll_width <= 375, (
                f"story-journey page scrollWidth is {scroll_width} with a long "
                f"unbreakable title, expected <= 375"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_story_journey_root_page_single_h1_and_story_links():
    """AC1-AC2: root story-journey.html has exactly one h1 and story links."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    pkg_dir = PACKAGE_DIR / tag
    data = json.loads((pkg_dir / "delivery-history.json").read_text())
    data["cards"] = [
        {"repo": "mqucifer/crew", "number": 127, "title": "Extract threshold logic"}
    ]
    (pkg_dir / "delivery-history.json").write_text(json.dumps(data))
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "story-journey.html").read_text()

        # AC1: exactly one h1 element in the document
        h1_count = len(re.findall(r"<h1[\s>]", html))
        assert h1_count == 1, f"found {h1_count} h1 elements, expected exactly 1"

        # AC2: the content section contains at least one anchor whose href
        # matches the pattern stories/
        content_start = html.index("</header>")
        content_html = html[content_start:]
        section_match = re.search(
            r'<section[^>]*>(.*?)</section>', content_html, re.DOTALL
        )
        assert section_match, "no section element found in content area"
        section_html = section_match.group(1)
        story_links = re.findall(
            r'<a[^>]*href="([^"]*stories/[^"]*)"[^>]*>', section_html
        )
        assert story_links, (
            f"no story links found in content section; "
            f"section content: {section_html[:200]}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cycle_time_stat_formats_hours_and_minutes():
    """AC1-AC4: the cycle time stat renders hours and minutes with exact text.

    Covers AC6 (the value span carries the 'num' class) and AC7 (the value
    never contains 'day' or 'days'), both named for the 89-minute case.
    """
    cases = [
        (89, "1 hr 29 min"),
        (60, "1 hr"),
        (0, "0 min"),
        (4320, "72 hr"),
    ]
    tag = "delivery-history-TEST"
    original = DELIVERY_HISTORY_TAG.read_text()
    try:
        for minutes, expected in cases:
            _make_fake_package(
                tag,
                ["Sprint 6"],
                metrics={
                    "Sprint 6": {
                        "throughput": 22,
                        "points_delivered": 63,
                        "first_attempt_numerator": 12,
                        "first_attempt_denominator": 22,
                        "escalation_count": 1,
                        "cycle_time_minutes": minutes,
                    }
                },
            )
            DELIVERY_HISTORY_TAG.write_text(tag + "\n")
            _build()
            html = (BUILD_DIR / "sprint-6.html").read_text()
            stats = _stats_section(html)
            cycle_stat = None
            for block in re.findall(
                r'<div class="stat">(.*?)</div>', stats, re.DOTALL
            ):
                if '<span class="stat__label">cycle time</span>' in block:
                    cycle_stat = block
                    break
            assert cycle_stat is not None, "no stat labelled 'cycle time' found"
            m = re.search(
                r'<span class="stat__value([^"]*)">(.*?)</span>',
                cycle_stat,
                re.DOTALL,
            )
            assert m, "cycle time stat has no .stat__value"
            value_text = m.group(2).strip()
            value_class = m.group(1).strip()
            assert value_text == expected, (
                f"cycle_time_minutes={minutes}: value is {value_text!r}, "
                f"expected {expected!r}"
            )
            if minutes == 89:
                assert "num" in value_class.split(), (
                    f"cycle time value class is {value_class!r}, "
                    "expected to include 'num'"
                )
                assert "day" not in value_text and "days" not in value_text, (
                    f"cycle time value {value_text!r} mentions days"
                )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _make_package_with_full_sprint(
    tag: str,
    stories: list[dict],
    cards: list[dict],
    failure_causes: list[dict],
    decided: list[dict],
) -> Path:
    """Create a fake package with stories, failure causes, and decided entries all populated."""
    sprints = [{"name": "Sprint 6", "start": "2026-09-22", "end": "2026-09-29"}]
    metrics = {
        "Sprint 6": {
            "throughput": len(stories),
            "points_delivered": 10,
            "first_attempt_numerator": 1,
            "first_attempt_denominator": max(len(stories), 1),
            "escalation_count": 0,
            "cycle_time_days": 2.0,
            "top_failure_causes": failure_causes,
        }
    }
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
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps(
            {
                "sprints": sprints,
                "cards": cards,
                "crew_repository": "mqucifer/crew",
                "sprint_metrics": {"answers": metrics},
                "analysis": {
                    "stories": stories,
                    "sprints": [{"sprint": "Sprint 6", "decided": decided}],
                },
            }
        )
    )
    return pkg_dir


def test_sprint_sections_stacked_at_phone_width():
    """AC1: at 375px, .sprint-side is below .sprint-chart and .sprint-decided is below .sprint-side."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 1,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "card.py",
        }
    ]
    failure_causes = [{"reason": "A test's assertion failed", "count": 3}]
    decided = [
        {
            "at": "2026-09-25T23:37:00",
            "kind": "design_revision",
            "number": 122,
            "repo": "mqucifer/crew",
            "text": "Design revision",
        }
    ]
    _make_package_with_full_sprint(tag, stories, cards, failure_causes, decided)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            chart_rect = page.locator(".sprint-chart").bounding_box()
            side_rect = page.locator(".sprint-side").bounding_box()
            decided_rect = page.locator(".sprint-decided").bounding_box()

            assert chart_rect, ".sprint-chart not found"
            assert side_rect, ".sprint-side not found"
            assert decided_rect, ".sprint-decided not found"

            chart_bottom = chart_rect["y"] + chart_rect["height"]
            side_bottom = side_rect["y"] + side_rect["height"]

            assert side_rect["y"] >= chart_bottom, (
                f".sprint-side top ({side_rect['y']}) should be >= "
                f".sprint-chart bottom ({chart_bottom})"
            )
            assert decided_rect["y"] >= side_bottom, (
                f".sprint-decided top ({decided_rect['y']}) should be >= "
                f".sprint-side bottom ({side_bottom})"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_sections_side_by_side_at_desktop_width():
    """AC2: at 1440px, .sprint-side left edge is at or after .sprint-chart right edge."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 1,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "card.py",
        }
    ]
    failure_causes = [{"reason": "A test's assertion failed", "count": 3}]
    decided = [
        {
            "at": "2026-09-25T23:37:00",
            "kind": "design_revision",
            "number": 122,
            "repo": "mqucifer/crew",
            "text": "Design revision",
        }
    ]
    _make_package_with_full_sprint(tag, stories, cards, failure_causes, decided)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            chart_rect = page.locator(".sprint-chart").bounding_box()
            side_rect = page.locator(".sprint-side").bounding_box()

            assert chart_rect, ".sprint-chart not found"
            assert side_rect, ".sprint-side not found"

            chart_right = chart_rect["x"] + chart_rect["width"]

            assert side_rect["x"] >= chart_right, (
                f".sprint-side left ({side_rect['x']}) should be >= "
                f".sprint-chart right ({chart_right})"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_chart_no_horizontal_overflow_at_phone_width():
    """AC3: at 375px with no failure-causes or decided, .sprint-chart scrollWidth == clientWidth."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 1,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "card.py",
        }
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const el = document.querySelector('.sprint-chart');
                    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
                })()
                """
            )

            assert result["scrollWidth"] == result["clientWidth"], (
                f".sprint-chart scrollWidth ({result['scrollWidth']}) != "
                f"clientWidth ({result['clientWidth']}) — horizontal overflow"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_heading_order_at_phone_width():
    """AC4: at 375px, h2 in .sprint-chart is above h2 in .sprint-side which is above h2 in .sprint-decided."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 1,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "card.py",
        }
    ]
    failure_causes = [{"reason": "A test's assertion failed", "count": 3}]
    decided = [
        {
            "at": "2026-09-25T23:37:00",
            "kind": "design_revision",
            "number": 122,
            "repo": "mqucifer/crew",
            "text": "Design revision",
        }
    ]
    _make_package_with_full_sprint(tag, stories, cards, failure_causes, decided)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            chart_h2 = page.locator(".sprint-chart h2").bounding_box()
            side_h2 = page.locator(".sprint-side h2").bounding_box()
            decided_h2 = page.locator(".sprint-decided h2").bounding_box()

            assert chart_h2, "h2 in .sprint-chart not found"
            assert side_h2, "h2 in .sprint-side not found"
            assert decided_h2, "h2 in .sprint-decided not found"

            assert chart_h2["y"] < side_h2["y"], (
                f"chart h2 top ({chart_h2['y']}) should be < side h2 top ({side_h2['y']})"
            )
            assert side_h2["y"] < decided_h2["y"], (
                f"side h2 top ({side_h2['y']}) should be < "
                f"decided h2 top ({decided_h2['y']})"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_headings_text_and_no_clipping_at_phone_width():
    """AC5: at 375px, chart h2 and side h2 have exact text and no horizontal clipping."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 1,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "card.py",
        }
    ]
    failure_causes = [{"reason": "A test's assertion failed", "count": 3}]
    decided = [
        {
            "at": "2026-09-25T23:37:00",
            "kind": "design_revision",
            "number": 122,
            "repo": "mqucifer/crew",
            "text": "Design revision",
        }
    ]
    _make_package_with_full_sprint(tag, stories, cards, failure_causes, decided)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            chart_h2_text = page.locator(".sprint-chart h2").inner_text()
            assert chart_h2_text == "The Architect's split, story by story", (
                f"chart h2 text is {chart_h2_text!r}"
            )

            side_h2_text = page.locator(".sprint-side h2").inner_text()
            assert side_h2_text == "Why work didn't land first time", (
                f"side h2 text is {side_h2_text!r}"
            )

            chart_scroll = page.evaluate(
                """
                (() => {
                    const el = document.querySelector('.sprint-chart h2');
                    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
                })()
                """
            )
            assert chart_scroll["scrollWidth"] == chart_scroll["clientWidth"], (
                f"chart h2 scrollWidth ({chart_scroll['scrollWidth']}) != "
                f"clientWidth ({chart_scroll['clientWidth']}) — heading clipped"
            )

            side_scroll = page.evaluate(
                """
                (() => {
                    const el = document.querySelector('.sprint-side h2');
                    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
                })()
                """
            )
            assert side_scroll["scrollWidth"] == side_scroll["clientWidth"], (
                f"side h2 scrollWidth ({side_scroll['scrollWidth']}) != "
                f"clientWidth ({side_scroll['clientWidth']}) — heading clipped"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_headings_aligned_at_desktop_width():
    """AC6: at 1440px, h2 in .sprint-chart top equals h2 in .sprint-side top."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 1,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "card.py",
        }
    ]
    failure_causes = [{"reason": "A test's assertion failed", "count": 3}]
    decided = [
        {
            "at": "2026-09-25T23:37:00",
            "kind": "design_revision",
            "number": 122,
            "repo": "mqucifer/crew",
            "text": "Design revision",
        }
    ]
    _make_package_with_full_sprint(tag, stories, cards, failure_causes, decided)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            chart_h2 = page.locator(".sprint-chart h2").bounding_box()
            side_h2 = page.locator(".sprint-side h2").bounding_box()

            assert chart_h2, "h2 in .sprint-chart not found"
            assert side_h2, "h2 in .sprint-side not found"

            assert abs(chart_h2["y"] - side_h2["y"]) < 1, (
                f"chart h2 top ({chart_h2['y']}) should equal "
                f"side h2 top ({side_h2['y']})"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_link_href_and_text():
    """AC1: attempt row contains an <a> with href to journey page and visible text with card id."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 125, "repo": "mqucifer/crew"},
                "blocks": ["refused", "landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 125,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "card.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        a_match = re.search(
            r'<a href="stories/mqucifer-crew-125\.html">(.*?)</a>',
            html,
            re.DOTALL,
        )
        assert a_match, "no <a> with href 'stories/mqucifer-crew-125.html' found in attempt row"
        link_inner = a_match.group(1)
        assert "#125" in link_inner, (
            f"link visible text does not include '#125': {link_inner!r}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_journey_page_file_exists_with_title():
    """AC2: built story journey file exists and its title contains the card number."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 114, "repo": "mqucifer/crew-presentation"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 114,
                "repo": "mqucifer/crew-presentation",
                "sprint": "Sprint 6",
                "title": "Link each story from the sprint page to its journey",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        journey_file = BUILD_DIR / "stories" / "mqucifer-crew-presentation-114.html"
        assert journey_file.is_file(), f"journey page not found at {journey_file}"
        content = journey_file.read_text()
        title_match = re.search(r"<title>(.*?)</title>", content, re.DOTALL)
        assert title_match, "no <title> element in journey page"
        assert "114" in title_match.group(1), (
            f"title is {title_match.group(1)!r}, expected to contain '114'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_journey_pages_exact_file_count():
    """AC3: two cards produce exactly two files in build/stories/."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 101, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            },
            {
                "card": {"number": 102, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            },
        ],
        cards=[
            {
                "number": 101,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "a.py",
            },
            {
                "number": 102,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "b.py",
            },
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        stories_dir = BUILD_DIR / "stories"
        assert stories_dir.is_dir(), "build/stories/ directory not found"
        files = sorted(f.name for f in stories_dir.iterdir() if f.is_file())
        assert files == ["mqucifer-crew-101.html", "mqucifer-crew-102.html"], (
            f"build/stories/ contains {files}, expected exactly two files"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_journey_page_slug_replaces_slash_with_single_hyphen():
    """AC4: repo 'org/team' number 77 produces build/stories/org-team-77.html."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 77, "repo": "org/team"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 77,
                "repo": "org/team",
                "sprint": "Sprint 6",
                "title": "x.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        expected_path = BUILD_DIR / "stories" / "org-team-77.html"
        assert expected_path.is_file(), f"expected {expected_path} to exist"
        stories_dir = BUILD_DIR / "stories"
        files = [f.name for f in stories_dir.iterdir() if f.is_file()]
        assert "org-team-77.html" in files, f"org-team-77.html not in {files}"
        assert "org--team-77.html" not in files, "double hyphen in slug"
        assert "orgteam-77.html" not in files, "empty string replacement in slug"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_journey_page_path_has_data_stage_five_when_delivered():
    """AC1: delivered story with blocks=['refused','landed'] renders a .path with a .path__step[data-stage='5']."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 100, "repo": "mqucifer/crew-presentation"},
                "blocks": ["refused", "landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 100,
                "repo": "mqucifer/crew-presentation",
                "sprint": "Sprint 6",
                "title": "A story's journey",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        journey_file = BUILD_DIR / "stories" / "mqucifer-crew-presentation-100.html"
        assert journey_file.is_file(), f"journey page not found at {journey_file}"
        html = journey_file.read_text()
        # Find the .path div
        path_match = re.search(r'<div class="path"[^>]*>(.*?)</div>\s*(?:</div>\s*)*</div>', html, re.DOTALL)
        assert path_match, "no <div class='path'> found in journey page"
        path_html = path_match.group(0)
        # Check for at least one .path__step with data-stage="5"
        step_match = re.search(
            r'<div class="path__step"\s+data-stage="5">', path_html
        )
        assert step_match, (
            "no .path__step with data-stage='5' found in the .path div"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_journey_page_path_step_without_data_stage_when_not_delivered():
    """AC2: undelivered story with blocks=[] renders a .path with a .path__step that has no data-stage."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 100, "repo": "mqucifer/crew-presentation"},
                "blocks": [],
                "crew_fixes": [],
                "delivered": False,
            }
        ],
        cards=[
            {
                "number": 100,
                "repo": "mqucifer/crew-presentation",
                "sprint": "Sprint 6",
                "title": "A story's journey",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        journey_file = BUILD_DIR / "stories" / "mqucifer-crew-presentation-100.html"
        assert journey_file.is_file(), f"journey page not found at {journey_file}"
        html = journey_file.read_text()
        # Find the .path div
        path_match = re.search(r'<div class="path"[^>]*>(.*?)</div>\s*(?:</div>\s*)*</div>', html, re.DOTALL)
        assert path_match, "no <div class='path'> found in journey page"
        path_html = path_match.group(0)
        # Check for at least one .path__step without a data-stage attribute
        steps = re.findall(r'<div class="path__step"[^>]*>', path_html)
        assert steps, "no .path__step elements found in the .path div"
        has_no_data_stage = any(
            "data-stage" not in step for step in steps
        )
        assert has_no_data_stage, (
            "all .path__step elements have a data-stage attribute; "
            "expected at least one without it"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_first_child_is_anchor_not_div():
    """AC5: every .attempt-row first child is an <a>, and no <a> has class 'attempt-row'."""
    tag = "delivery-history-TEST"
    story_numbers = [101, 102, 103]
    stories = [
        {
            "card": {"number": n, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        }
        for n in story_numbers
    ]
    cards = [
        {
            "number": n,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": f"s{n}.py",
        }
        for n in story_numbers
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row")
            results = page.evaluate("""
                () => Array.from(document.querySelectorAll('.attempt-row')).map(row => {
                    const first = row.firstElementChild;
                    return {
                        tag: first.tagName,
                        hasAttemptRowClass: first.classList.contains('attempt-row'),
                    };
                })
            """)
            assert len(results) == 3, f"expected 3 rows, got {len(results)}"
            for i, r in enumerate(results):
                assert r["tag"] == "A", (
                    f"row {i}: first child is <{r['tag'].lower()}>, expected <a>"
                )
                assert not r["hasAttemptRowClass"], (
                    f"row {i}: <a> has class 'attempt-row'"
                )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_link_has_no_target_attribute():
    """AC6: the <a> in an attempt row has no target attribute."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 125, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 125,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "card.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row a")
            has_target = page.evaluate("""
                () => {
                    const a = document.querySelector('.attempt-row a');
                    return a.hasAttribute('target');
                }
            """)
            assert not has_target, (
                "the <a> element has a 'target' attribute; expected none"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_link_color_light_theme():
    """AC7: light-theme computed colour of the <a> is rgb(168, 74, 22)."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 125, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 125,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "card.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row a")
            page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
            page.wait_for_timeout(100)
            color = page.evaluate(
                "getComputedStyle(document.querySelector('.attempt-row a')).color"
            )
            assert color == "rgb(168, 74, 22)", (
                f"light-theme link color is {color!r}, expected rgb(168, 74, 22)"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_link_color_dark_theme():
    """AC8: dark-theme computed colour of the <a> is rgb(224, 138, 74)."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 125, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 125,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "card.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row a")
            page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
            # The design system animates colour on a theme change; wait for the
            # link's colour to settle at its dark-theme value before reading it.
            page.wait_for_function(
                "() => getComputedStyle(document.querySelector('.attempt-row a'))"
                ".color === 'rgb(224, 138, 74)'",
                timeout=2000,
            )
            color = page.evaluate(
                "getComputedStyle(document.querySelector('.attempt-row a')).color"
            )
            assert color == "rgb(224, 138, 74)", (
                f"dark-theme link color is {color!r}, expected rgb(224, 138, 74)"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_link_focus_outline():
    """AC9: focused <a> has outline-width > 0 and outline-style not none."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 125, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 125,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "card.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row a")
            page.evaluate("document.querySelector('.attempt-row a').focus()")
            outline_width = page.evaluate(
                "getComputedStyle(document.querySelector('.attempt-row a')).outlineWidth"
            )
            outline_style = page.evaluate(
                "getComputedStyle(document.querySelector('.attempt-row a')).outlineStyle"
            )
            assert outline_style != "none", (
                f"outline-style is {outline_style!r}, expected not 'none'"
            )
            width_px = float(outline_width.rstrip("px"))
            assert width_px > 0, (
                f"outline-width is {outline_width!r}, expected > 0px"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_lead_time_minutes_format():
    """AC2, AC6: lead_time_minutes renders 'lead time' label and minute values."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 7",
        [
            {
                "text": "Lead time increased",
                "measure": "lead_time_minutes",
                "previous": 29,
                "now": 45,
                "better": False,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        section_match = re.search(
            r'<section class="card changed-trend".*?</section>',
            html,
            re.DOTALL,
        )
        assert section_match, "changed-trend section not found"
        section_html = section_match.group(0)
        # AC6: label is 'lead time', not the raw measure name
        pos_label = section_html.index("lead time")
        assert "lead_time_minutes" not in section_html, (
            "raw measure name 'lead_time_minutes' appears in changed-trend section"
        )
        # AC2: values show minutes
        pos_prev = section_html.index("29 min")
        pos_now = section_html.index("45 min")
        assert pos_label < pos_prev < pos_now, (
            f"reading order violated: label@{pos_label}, "
            f"prev@{pos_prev}, now@{pos_now}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_non_time_measure_no_unit():
    """AC3, AC8: first_attempt_rate_percent shows bare numbers, no time unit."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 7",
        [
            {
                "text": "First-attempt rate rose",
                "measure": "first_attempt_rate_percent",
                "previous": 40,
                "now": 55,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        # AC3: values are bare numbers in num spans
        assert 'class="num">40<' in html, (
            "previous value is not '40' in a num span"
        )
        assert 'class="num">55<' in html, (
            "now value is not '55' in a num span"
        )
        # AC8: no time-unit substring in the span text
        values_div = re.search(
            r'class="changed-trend-values">(.*?)</div>', html, re.DOTALL
        )
        assert values_div, "no changed-trend-values div found"
        spans = re.findall(r'class="num">(.*?)<', values_div.group(1))
        assert len(spans) == 2, f"expected 2 num spans, got {len(spans)}"
        for span_text in spans:
            assert "hr" not in span_text, f"span text {span_text!r} contains 'hr'"
            assert "min" not in span_text, f"span text {span_text!r} contains 'min'"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_zero_minutes():
    """AC4: cycle_time_minutes with 0 shows '0 min' for both values."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 7",
        [
            {
                "text": "Cycle time held",
                "measure": "cycle_time_minutes",
                "previous": 0,
                "now": 0,
                "better": False,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        assert 'class="num">0 min<' in html, (
            "zero cycle_time_minutes does not render '0 min'"
        )
        count = html.count('class="num">0 min<')
        assert count >= 2, f"expected at least 2 '0 min' values, found {count}"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_label_and_blocks_no_truncation_phone():
    """AC1: at 375px, #127's label and .blocks have no horizontal clipping."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 127, "repo": "mqucifer/crew"},
            "blocks": [
                "refused", "refused", "refused", "refused",
                "refused", "refused", "landed",
            ],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 127,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "thresholds.py",
        }
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.attempt-row');
                    const row = Array.from(rows).find(r => r.textContent.includes('#127'));
                    if (!row) return null;
                    const label = row.querySelector('a');
                    const blocks = row.querySelector('.blocks');
                    return {
                        labelScroll: label.scrollWidth,
                        labelClient: label.clientWidth,
                        blocksScroll: blocks.scrollWidth,
                        blocksClient: blocks.clientWidth,
                    };
                })()
                """
            )
            assert result is not None, "attempt-row for #127 not found"
            assert result["labelScroll"] == result["labelClient"], (
                f"label scrollWidth ({result['labelScroll']}) != "
                f"clientWidth ({result['labelClient']}) — horizontal clipping"
            )
            assert result["blocksScroll"] == result["blocksClient"], (
                f".blocks scrollWidth ({result['blocksScroll']}) != "
                f"clientWidth ({result['blocksClient']}) — horizontal clipping"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_no_overflow_8_blocks_phone():
    """AC2: at 375px, the .attempt-row for a story with 8 blocks has scrollWidth == clientWidth."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 133, "repo": "mqucifer/crew"},
            "blocks": [
                "refused", "refused", "refused", "refused",
                "refused", "refused", "refused", "landed",
            ],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 133,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "metrics.py",
        }
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.attempt-row');
                    const row = Array.from(rows).find(r => r.textContent.includes('#133'));
                    if (!row) return null;
                    return {
                        scrollWidth: row.scrollWidth,
                        clientWidth: row.clientWidth,
                    };
                })()
                """
            )
            assert result is not None, "attempt-row for #133 not found"
            assert result["scrollWidth"] == result["clientWidth"], (
                f".attempt-row scrollWidth ({result['scrollWidth']}) != "
                f"clientWidth ({result['clientWidth']}) — horizontal overflow"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_first_column_width_desktop():
    """AC3: at 1440px, the first column of .attempt-row is 170px (desktop unchanged)."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 1,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "card.py",
        }
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const row = document.querySelector('.attempt-row');
                    const firstChild = row.firstElementChild;
                    return { width: firstChild.offsetWidth };
                })()
                """
            )
            assert result["width"] == 170, (
                f"first column width is {result['width']}, expected 170"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_status_merged_no_truncation_phone():
    """AC4: at 375px, #125's .attempt-status has text 'merged' and no horizontal clipping."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 125, "repo": "mqucifer/crew"},
            "blocks": ["refused", "refused", "refused", "refused", "landed"],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 125,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "card.py",
        }
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.attempt-row');
                    const row = Array.from(rows).find(r => r.textContent.includes('#125'));
                    if (!row) return null;
                    const status = row.querySelector('.attempt-status');
                    return {
                        text: status.textContent,
                        scrollWidth: status.scrollWidth,
                        clientWidth: status.clientWidth,
                    };
                })()
                """
            )
            assert result is not None, "attempt-row for #125 not found"
            assert result["text"] == "merged", (
                f"status text is '{result['text']}', expected 'merged'"
            )
            assert result["scrollWidth"] == result["clientWidth"], (
                f".attempt-status scrollWidth ({result['scrollWidth']}) != "
                f"clientWidth ({result['clientWidth']}) — horizontal clipping"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_blocks_retain_40px_width_phone():
    """AC5: at 375px, each of the 8 .attempt-block elements has a computed width of 40px."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 133, "repo": "mqucifer/crew"},
            "blocks": [
                "refused", "refused", "refused", "refused",
                "refused", "refused", "refused", "landed",
            ],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 133,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "metrics.py",
        }
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.attempt-row');
                    const row = Array.from(rows).find(r => r.textContent.includes('#133'));
                    if (!row) return null;
                    const blocks = row.querySelectorAll('.attempt-block');
                    return Array.from(blocks).map(
                        b => parseInt(getComputedStyle(b).width, 10)
                    );
                })()
                """
            )
            assert result is not None, "attempt-row for #133 not found"
            assert len(result) == 8, f"expected 8 blocks, got {len(result)}"
            for i, w in enumerate(result):
                assert w == 40, f"block {i} width is {w}px, expected 40px"

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_status_first_try_no_truncation_phone():
    """AC6: at 375px, #128's .attempt-status has text 'first try' and no horizontal clipping."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 128, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "first_try",
        }
    ]
    cards = [
        {
            "number": 128,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "report.py",
        }
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.attempt-row');
                    const row = Array.from(rows).find(r => r.textContent.includes('#128'));
                    if (!row) return null;
                    const status = row.querySelector('.attempt-status');
                    return {
                        text: status.textContent,
                        scrollWidth: status.scrollWidth,
                        clientWidth: status.clientWidth,
                    };
                })()
                """
            )
            assert result is not None, "attempt-row for #128 not found"
            assert result["text"] == "first try", (
                f"status text is '{result['text']}', expected 'first try'"
            )
            assert result["scrollWidth"] == result["clientWidth"], (
                f".attempt-status scrollWidth ({result['scrollWidth']}) != "
                f"clientWidth ({result['clientWidth']}) — horizontal clipping"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_row_div_no_overflow_7_blocks_phone():
    """AC7: at 375px, the .attempt-row div for #127 has scrollWidth == clientWidth."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 127, "repo": "mqucifer/crew"},
            "blocks": [
                "refused", "refused", "refused", "refused",
                "refused", "refused", "landed",
            ],
            "crew_fixes": [],
            "delivered": True,
        }
    ]
    cards = [
        {
            "number": 127,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "thresholds.py",
        }
    ]
    _make_package_with_stories(tag, stories=stories, cards=cards)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.attempt-row');
                    const row = Array.from(rows).find(r => r.textContent.includes('#127'));
                    if (!row) return null;
                    return {
                        scrollWidth: row.scrollWidth,
                        clientWidth: row.clientWidth,
                    };
                })()
                """
            )
            assert result is not None, "attempt-row for #127 not found"
            assert result["scrollWidth"] == result["clientWidth"], (
                f".attempt-row scrollWidth ({result['scrollWidth']}) != "
                f"clientWidth ({result['clientWidth']}) — horizontal overflow"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_label_no_truncation_phone():
    """AC1: at 375px, the failure-cause label is not truncated or clipped."""
    tag = "delivery-history-TEST"
    causes = [{"reason": "test_assertion_failed", "count": 10}]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 1,
                "points_delivered": 10,
                "first_attempt_numerator": 0,
                "first_attempt_denominator": 1,
                "escalation_count": 0,
                "cycle_time_days": 1.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.cause-row');
                    const row = Array.from(rows).find(
                        r => r.textContent.includes("A test's assertion failed")
                    );
                    if (!row) return null;
                    const label = row.querySelector(':first-child');
                    return {
                        scrollWidth: label.scrollWidth,
                        clientWidth: label.clientWidth,
                    };
                })()
                """
            )
            assert result is not None, "cause-row for 'A test's assertion failed' not found"
            assert result["scrollWidth"] == result["clientWidth"], (
                f"label scrollWidth ({result['scrollWidth']}) != "
                f"clientWidth ({result['clientWidth']}) — label truncated or clipped"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_bar_visible_and_proportional_phone():
    """AC2: at 375px, the .cause-bar has width > 0 and <= 100% of its parent's width."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "A test's assertion failed", "count": 10},
        {"reason": '"already exists"', "count": 6},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 2,
                "points_delivered": 10,
                "first_attempt_numerator": 0,
                "first_attempt_denominator": 2,
                "escalation_count": 0,
                "cycle_time_days": 1.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.cause-row');
                    const results = [];
                    rows.forEach(row => {
                        const bar = row.querySelector('.cause-bar');
                        const parent = bar.parentElement;
                        results.push({
                            barWidth: bar.offsetWidth,
                            parentWidth: parent.offsetWidth,
                        });
                    });
                    return results;
                })()
                """
            )
            assert result, "no .cause-bar elements found"
            for i, r in enumerate(result):
                assert r["barWidth"] > 0, (
                    f"bar {i} has width 0 — not visible"
                )
                assert r["barWidth"] <= r["parentWidth"], (
                    f"bar {i} width ({r['barWidth']}) exceeds parent "
                    f"width ({r['parentWidth']})"
                )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_row_first_column_width_desktop():
    """AC3: at 1440px, the first column of .cause-row is 210px (desktop unchanged)."""
    tag = "delivery-history-TEST"
    causes = [{"reason": "A test's assertion failed", "count": 10}]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 1,
                "points_delivered": 10,
                "first_attempt_numerator": 0,
                "first_attempt_denominator": 1,
                "escalation_count": 0,
                "cycle_time_days": 1.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const row = document.querySelector('.cause-row');
                    if (!row) return null;
                    const firstChild = row.firstElementChild;
                    return { width: firstChild.offsetWidth };
                })()
                """
            )
            assert result is not None, ".cause-row not found"
            assert result["width"] == 210, (
                f"first column width is {result['width']}, expected 210"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_count_visible_no_clipping_phone():
    """AC4: at 375px, the .num in the first .cause-row has text '10' and no clipping."""
    tag = "delivery-history-TEST"
    causes = [{"reason": "A test's assertion failed", "count": 10}]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 1,
                "points_delivered": 10,
                "first_attempt_numerator": 0,
                "first_attempt_denominator": 1,
                "escalation_count": 0,
                "cycle_time_days": 1.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const row = document.querySelector('.cause-row');
                    if (!row) return null;
                    const num = row.querySelector('.num');
                    if (!num) return null;
                    return {
                        text: num.textContent,
                        scrollWidth: num.scrollWidth,
                        clientWidth: num.clientWidth,
                    };
                })()
                """
            )
            assert result is not None, ".num element not found in first .cause-row"
            assert result["text"] == "10", (
                f".num text is '{result['text']}', expected '10'"
            )
            assert result["scrollWidth"] == result["clientWidth"], (
                f".num scrollWidth ({result['scrollWidth']}) != "
                f"clientWidth ({result['clientWidth']}) — count clipped"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_rows_six_in_order_phone():
    """AC5: at 375px, .cause-chart has exactly 6 rows with correct text in order."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "test_assertion_failed", "count": 10},
        {"reason": "already_exists", "count": 6},
        {"reason": "must_create_or_edit_file", "count": 3},
        {"reason": "undefined_name", "count": 2},
        {"reason": "no_test_written", "count": 2},
        {"reason": "unrecorded", "count": 2},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const chart = document.querySelector('.cause-chart');
                    if (!chart) return null;
                    const rows = chart.querySelectorAll('.cause-row');
                    const labels = Array.from(rows).map(
                        r => r.querySelector(':first-child').textContent
                    );
                    return { count: rows.length, labels };
                })()
                """
            )
            assert result is not None, ".cause-chart not found"
            assert result["count"] == 6, (
                f"expected 6 .cause-row children, got {result['count']}"
            )
            expected = [
                "A test's assertion failed",
                '"already exists"',
                "Must create or edit a file",
                "Undefined name (lint)",
                "No test written",
                "Cause not recorded",
            ]
            assert result["labels"] == expected, (
                f"label order mismatch: {result['labels']}"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_unrecorded_label_meta_class_phone():
    """AC6: at 375px, the 'Cause not recorded' label has class 'meta' and no clipping."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "test_assertion_failed", "count": 10},
        {"reason": "unrecorded", "count": 2},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 2,
                "points_delivered": 10,
                "first_attempt_numerator": 1,
                "first_attempt_denominator": 2,
                "escalation_count": 0,
                "cycle_time_days": 1.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.cause-row');
                    const row = Array.from(rows).find(
                        r => r.textContent.includes('Cause not recorded')
                    );
                    if (!row) return null;
                    const label = row.querySelector(':first-child');
                    return {
                        hasMeta: label.classList.contains('meta'),
                        scrollWidth: label.scrollWidth,
                        clientWidth: label.clientWidth,
                    };
                })()
                """
            )
            assert result is not None, "cause-row for 'Cause not recorded' not found"
            assert result["hasMeta"], (
                "unrecorded label should have class 'meta'"
            )
            assert result["scrollWidth"] == result["clientWidth"], (
                f"label scrollWidth ({result['scrollWidth']}) != "
                f"clientWidth ({result['clientWidth']}) — truncated"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_rows_no_horizontal_overflow_phone():
    """AC7: at 375px, each .cause-row has scrollWidth == clientWidth."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "test_assertion_failed", "count": 10},
        {"reason": "already_exists", "count": 6},
        {"reason": "must_create_or_edit_file", "count": 3},
        {"reason": "undefined_name", "count": 2},
        {"reason": "no_test_written", "count": 2},
        {"reason": "unrecorded", "count": 2},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            result = page.evaluate(
                """
                (() => {
                    const rows = document.querySelectorAll('.cause-row');
                    const results = [];
                    rows.forEach(row => {
                        results.push({
                            scrollWidth: row.scrollWidth,
                            clientWidth: row.clientWidth,
                        });
                    });
                    return results;
                })()
                """
            )
            assert result, "no .cause-row elements found"
            for i, r in enumerate(result):
                assert r["scrollWidth"] == r["clientWidth"], (
                    f"cause-row {i}: scrollWidth ({r['scrollWidth']}) != "
                    f"clientWidth ({r['clientWidth']}) — horizontal overflow"
                )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _make_package_cycle_time(
    tag: str,
    sprint_name: str,
    cycle_time_minutes: int,
    changed: list[dict],
) -> Path:
    """Create a fake package with cycle_time_minutes in metrics and custom changed entries."""
    sprints = [{"name": sprint_name, "start": "2026-09-22", "end": "2026-09-29"}]
    metrics = {
        sprint_name: {
            "throughput": 5,
            "points_delivered": 10,
            "first_attempt_numerator": 3,
            "first_attempt_denominator": 5,
            "escalation_count": 0,
            "cycle_time_days": round(cycle_time_minutes / 1440, 2),
            "cycle_time_minutes": cycle_time_minutes,
        }
    }
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
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps(
            {
                "sprints": sprints,
                "cards": [],
                "crew_repository": "mqucifer/crew",
                "sprint_metrics": {"answers": metrics},
                "analysis": {"sprints": [{"sprint": sprint_name, "changed": changed}]},
            }
        )
    )
    return pkg_dir


def _read_cycle_time(html: str) -> tuple[str | None, str | None]:
    """Read the cycle-time stat value and the trend now-value from rendered HTML.

    Returns (stat_text, trend_now). stat_text is None if no stat found.
    trend_now is None if no trend entry with label 'cycle time' is present.
    """
    stat_text = None
    stats = _stats_section(html)
    for block in re.findall(r'<div class="stat">(.*?)</div>', stats, re.DOTALL):
        if '<span class="stat__label">cycle time</span>' in block:
            m = re.search(
                r'<span class="stat__value[^"]*">(.*?)</span>', block, re.DOTALL
            )
            if m:
                stat_text = m.group(1).strip()
            break

    trend_now = None
    section_match = re.search(
        r'<section class="card changed-trend".*?</section>', html, re.DOTALL
    )
    if section_match:
        section_html = section_match.group(0)
        for entry_match in re.finditer(
            r'<div class="changed-trend-values">(.*?)</div>', section_html, re.DOTALL
        ):
            entry_html = entry_match.group(1)
            if "cycle time:" in entry_html:
                nums = re.findall(r'<span class="num">(.*?)</span>', entry_html)
                if len(nums) >= 2:
                    trend_now = nums[1].strip()
                break

    return stat_text, trend_now


def test_cycle_time_stat_matches_trend_now_value():
    """AC1: the cycle-time stat and the trend now-value render the same text."""
    tag = "delivery-history-TEST"
    _make_package_cycle_time(
        tag,
        "Sprint 6",
        cycle_time_minutes=4608,
        changed=[
            {
                "text": "Cycle time improved",
                "measure": "cycle_time_days",
                "previous": 5.2,
                "now": 3.2,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        stat_text, trend_now = _read_cycle_time(html)
        assert stat_text == "76 hr 48 min", (
            f"stat text is {stat_text!r}, expected '76 hr 48 min'"
        )
        assert trend_now == "76 hr 48 min", (
            f"trend now-value is {trend_now!r}, expected '76 hr 48 min'"
        )
        assert stat_text == trend_now, (
            f"stat ({stat_text!r}) and trend ({trend_now!r}) disagree"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cycle_time_stat_mismatch_names_both_values():
    """AC2: when the stat and trend disagree, the assertion names both values."""
    tag = "delivery-history-TEST"
    _make_package_cycle_time(
        tag,
        "Sprint 6",
        cycle_time_minutes=4608,
        changed=[
            {
                "text": "Cycle time worsened",
                "measure": "cycle_time_days",
                "previous": 3.2,
                "now": 4.1,
                "better": False,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        stat_text, trend_now = _read_cycle_time(html)
        assert stat_text == "76 hr 48 min", (
            f"stat text is {stat_text!r}, expected '76 hr 48 min'"
        )
        assert trend_now == "98 hr 24 min", (
            f"trend now-value is {trend_now!r}, expected '98 hr 24 min'"
        )
        with pytest.raises(AssertionError) as exc_info:
            assert stat_text == trend_now
        msg = str(exc_info.value)
        assert "76 hr 48 min" in msg, f"assertion message missing stat value: {msg!r}"
        assert "98 hr 24 min" in msg, f"assertion message missing trend value: {msg!r}"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cycle_time_no_trend_entry_passes_without_comparison():
    """AC3: when changed is empty, no trend entry exists and the test passes."""
    tag = "delivery-history-TEST"
    _make_package_cycle_time(
        tag,
        "Sprint 6",
        cycle_time_minutes=4608,
        changed=[],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        stat_text, trend_now = _read_cycle_time(html)
        assert stat_text == "76 hr 48 min", (
            f"stat text is {stat_text!r}, expected '76 hr 48 min'"
        )
        assert trend_now is None, (
            f"expected no cycle-time trend entry, got {trend_now!r}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _read_lead_time(html: str) -> str | None:
    """Read the lead-time trend now-value from rendered HTML.

    Returns the now-value (second .num span) of the first changed-trend entry
    labelled 'lead time', or None if no such entry is present.
    """
    section_match = re.search(
        r'<section class="card changed-trend".*?</section>', html, re.DOTALL
    )
    if not section_match:
        return None
    section_html = section_match.group(0)
    for entry_match in re.finditer(
        r'<div class="changed-trend-values">(.*?)</div>', section_html, re.DOTALL
    ):
        entry_html = entry_match.group(1)
        if "lead time:" in entry_html:
            nums = re.findall(r'<span class="num">(.*?)</span>', entry_html)
            if len(nums) >= 2:
                return nums[1].strip()
            break
    return None


def _make_package_lead_time(
    tag: str,
    sprint_name: str,
    lead_time_days: float,
    changed: list[dict],
) -> Path:
    """Create a fake package with lead_time_days in metrics and custom changed entries."""
    sprints = [{"name": sprint_name, "start": "2026-09-22", "end": "2026-09-29"}]
    metrics = {
        sprint_name: {
            "throughput": 5,
            "points_delivered": 10,
            "first_attempt_numerator": 3,
            "first_attempt_denominator": 5,
            "escalation_count": 0,
            "cycle_time_days": 2.0,
            "lead_time_days": lead_time_days,
        }
    }
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
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps(
            {
                "sprints": sprints,
                "cards": [],
                "crew_repository": "mqucifer/crew",
                "sprint_metrics": {"answers": metrics},
                "analysis": {"sprints": [{"sprint": sprint_name, "changed": changed}]},
            }
        )
    )
    return pkg_dir


def _lead_time_expected(lead_time_days: float) -> str:
    """The displayed text the package's lead_time_days should format to.

    Mirrors the build: lead_time_days is converted to whole minutes, then to
    hours and minutes ('120 hr', '175 hr 12 min', '0 min').
    """
    total_minutes = round(lead_time_days * 24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours == 0:
        return f"{minutes} min"
    if minutes == 0:
        return f"{hours} hr"
    return f"{hours} hr {minutes} min"


def test_lead_time_trend_matches_package_lead_time_days():
    """AC1: the lead-time trend now-value matches the package's lead_time_days."""
    tag = "delivery-history-TEST"
    lead_time_days = 5.0
    _make_package_lead_time(
        tag,
        "Sprint 7",
        lead_time_days=lead_time_days,
        changed=[
            {
                "text": "Lead time improved",
                "measure": "lead_time_days",
                "previous": 7.0,
                "now": 5.0,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        trend_now = _read_lead_time(html)
        expected = _lead_time_expected(lead_time_days)
        assert expected == "120 hr", (
            f"package-derived value is {expected!r}, expected '120 hr'"
        )
        assert trend_now == expected, (
            f"lead-time trend now-value is {trend_now!r}, "
            f"expected {expected!r} from lead_time_days={lead_time_days}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_lead_time_trend_mismatch_names_both_values():
    """AC2: a trend now-value that disagrees with lead_time_days fails, naming both."""
    tag = "delivery-history-TEST"
    lead_time_days = 5.0
    _make_package_lead_time(
        tag,
        "Sprint 7",
        lead_time_days=lead_time_days,
        changed=[
            {
                "text": "Lead time worsened",
                "measure": "lead_time_days",
                "previous": 7.0,
                "now": 7.3,
                "better": False,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        trend_now = _read_lead_time(html)
        expected = _lead_time_expected(lead_time_days)
        assert trend_now == "175 hr 12 min", (
            f"trend now-value is {trend_now!r}, expected '175 hr 12 min'"
        )
        assert expected == "120 hr", (
            f"package-derived value is {expected!r}, expected '120 hr'"
        )
        with pytest.raises(AssertionError) as exc_info:
            assert trend_now == expected
        msg = str(exc_info.value)
        assert "120 hr" in msg, f"assertion message missing package value: {msg!r}"
        assert "175 hr 12 min" in msg, f"assertion message missing trend value: {msg!r}"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_lead_time_no_trend_entry_passes_without_comparison():
    """AC3: with no lead_time_days entry, no trend value exists and the check passes."""
    tag = "delivery-history-TEST"
    lead_time_days = 5.0
    _make_package_lead_time(
        tag,
        "Sprint 7",
        lead_time_days=lead_time_days,
        changed=[
            {
                "text": "Cycle time improved",
                "measure": "cycle_time_days",
                "previous": 7.0,
                "now": 5.0,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        trend_now = _read_lead_time(html)
        assert trend_now is None, (
            f"expected no lead-time trend entry, got {trend_now!r}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _make_package_first_attempt(
    tag: str,
    numerator: int,
    denominator: int,
    stories: list[dict],
    cards: list[dict],
    sprint_names: list[str] | None = None,
) -> Path:
    """Create a fake package with custom first-try metrics and stories."""
    if sprint_names is None:
        sprint_names = ["Sprint 6"]
    sprints = [
        {"name": n, "start": "2026-09-22", "end": "2026-09-29"}
        for n in sprint_names
    ]
    metrics = {
        name: {
            "throughput": len(stories),
            "points_delivered": 10,
            "first_attempt_numerator": numerator,
            "first_attempt_denominator": denominator,
            "escalation_count": 0,
            "cycle_time_days": 2.0,
        }
        for name in sprint_names
    }
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
    (pkg_dir / "delivery-history.json").write_text(
        json.dumps(
            {
                "sprints": sprints,
                "cards": cards,
                "crew_repository": "mqucifer/crew",
                "sprint_metrics": {"answers": metrics},
                "analysis": {"stories": stories},
            }
        )
    )
    return pkg_dir


def test_non_first_try_count_matches_stat_ac1():
    """AC1: attempt-chart rows match the stat: exactly denominator rows,
    numerator 'first try' badges, and the remainder 'merged'."""
    tag = "delivery-history-TEST"
    # 5 stories: 3 with pattern first_try, 2 with pattern retried.
    stories = [
        {
            "card": {"number": i, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "first_try" if i <= 3 else "retried",
        }
        for i in range(1, 6)
    ]
    cards = [
        {
            "number": i,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": f"story-{i}.py",
        }
        for i in range(1, 6)
    ]
    _make_package_first_attempt(
        tag,
        numerator=3,
        denominator=5,
        stories=stories,
        cards=cards,
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row")

            row_count = page.evaluate("""
                () => document.querySelectorAll('.attempt-chart .attempt-row').length
            """)
            first_try_count = page.evaluate("""
                () => Array.from(document.querySelectorAll('.attempt-chart .attempt-row'))
                    .filter(row => {
                        const status = row.querySelector('.attempt-status');
                        return status && status.textContent.trim() === 'first try';
                    }).length
            """)
            retried_count = page.evaluate("""
                () => Array.from(document.querySelectorAll('.attempt-chart .attempt-row'))
                    .filter(row => {
                        const status = row.querySelector('.attempt-status');
                        return status && status.textContent.trim() === 'retried';
                    }).length
            """)

            assert row_count == 5, f"expected 5 rows, found {row_count}"
            assert first_try_count == 3, f"expected 3 'first try', found {first_try_count}"
            assert retried_count == 2, f"expected 2 'retried', found {retried_count}"
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_non_first_try_count_mismatch_names_both_values():
    """AC1b: even when some stories have no matching card entry, the chart
    still shows denominator rows with the correct badge split."""
    tag = "delivery-history-TEST"
    # 12 first-try stories (all rendered)
    stories_first_try = [
        {
            "card": {"number": i, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "first_try",
        }
        for i in range(1, 13)
    ]
    # 10 not-first-try stories (all in analysis.stories, but only 8 have cards)
    stories_not_first = [
        {
            "card": {"number": i, "repo": "mqucifer/crew"},
            "blocks": ["refused", "landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "retried",
        }
        for i in range(13, 23)
    ]
    stories = stories_first_try + stories_not_first
    # Cards for all 12 first-try + only 8 of the 10 not-first-try (stories 13-20)
    # Stories 21-22 have no matching card entry (orphaned)
    cards = [
        {
            "number": i,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": f"story-{i}.py",
        }
        for i in list(range(1, 13)) + list(range(13, 21))
    ]
    _make_package_first_attempt(
        tag,
        numerator=12,
        denominator=22,
        stories=stories,
        cards=cards,
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row")

            row_count = page.evaluate("""
                () => document.querySelectorAll('.attempt-chart .attempt-row').length
            """)
            non_first_try_count = page.evaluate("""
                () => Array.from(document.querySelectorAll('.attempt-chart .attempt-row'))
                    .filter(row => {
                        const status = row.querySelector('.attempt-status');
                        return status && status.textContent.trim() !== 'first try';
                    }).length
            """)

            stat_text = page.evaluate("""
                () => {
                    const labels = document.querySelectorAll('.stat__label');
                    for (const label of labels) {
                        if (label.textContent.trim() === 'landed first try') {
                            const stat = label.closest('.stat');
                            return stat.querySelector('.stat__value').textContent.trim();
                        }
                    }
                    return null;
                }
            """)
            parts = stat_text.split()
            numerator = int(parts[0])
            denominator = int(parts[2])
            expected_non_first = denominator - numerator

            assert row_count == denominator, (
                f"expected {denominator} rows, found {row_count}"
            )
            assert non_first_try_count == expected_non_first, (
                f"expected {expected_non_first} non-first-try rows "
                f"(denominator {denominator} minus numerator {numerator}), "
                f"found {non_first_try_count}"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_non_first_try_count_all_first_try():
    """AC3: all stories are first-try, so the count of non-first-try rows is 0, equal to 5-5."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": i, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "first_try",
        }
        for i in range(1, 6)
    ]
    cards = [
        {
            "number": i,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": f"story-{i}.py",
        }
        for i in range(1, 6)
    ]
    _make_package_first_attempt(
        tag,
        numerator=5,
        denominator=5,
        stories=stories,
        cards=cards,
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row")

            non_first_try_count = page.evaluate("""
                () => Array.from(document.querySelectorAll('.attempt-row'))
                    .filter(row => {
                        const status = row.querySelector('.attempt-status');
                        return status && status.textContent.trim() !== 'first try';
                    }).length
            """)

            stat_text = page.evaluate("""
                () => {
                    const labels = document.querySelectorAll('.stat__label');
                    for (const label of labels) {
                        if (label.textContent.trim() === 'landed first try') {
                            const stat = label.closest('.stat');
                            return stat.querySelector('.stat__value').textContent.trim();
                        }
                    }
                    return null;
                }
            """)
            parts = stat_text.split()
            numerator = int(parts[0])
            denominator = int(parts[2])
            expected = denominator - numerator

            assert non_first_try_count == 0, (
                f"expected 0 non-first-try rows, found {non_first_try_count}"
            )
            assert expected == 0, (
                f"expected denominator minus numerator to be 0, got {expected}"
            )
            assert non_first_try_count == expected, (
                f"expected {expected} non-first-try rows "
                f"(denominator {denominator} minus numerator {numerator}), "
                f"found {non_first_try_count}"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_attempt_chart_rows_match_stat_when_cards_missing_ac2():
    """AC2: when only 1 of 3 stories has a matching card entry, the chart
    still shows exactly denominator (3) rows, not fewer."""
    tag = "delivery-history-TEST"
    # 3 stories: 2 with blocks=["landed"], 1 with blocks=["refused", "landed"]
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        },
        {
            "card": {"number": 2, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
        },
        {
            "card": {"number": 3, "repo": "mqucifer/crew"},
            "blocks": ["refused", "landed"],
            "crew_fixes": [],
            "delivered": True,
        },
    ]
    # Only 1 card entry with sprint="Sprint 6" (the other 2 stories have no matching card)
    cards = [
        {
            "number": 1,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": "story-1.py",
        }
    ]
    _make_package_first_attempt(
        tag,
        numerator=2,
        denominator=3,
        stories=stories,
        cards=cards,
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".attempt-row")

            row_count = page.evaluate("""
                () => document.querySelectorAll('.attempt-chart .attempt-row').length
            """)

            assert row_count == 3, (
                f"expected exactly 3 attempt-row elements, found {row_count}"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_pattern_retried_not_labeled_first_try():
    """AC1: a story with pattern 'retried' does not display 'first try' even when
    first_attempt_numerator equals the total story count."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "first_try",
        },
        {
            "card": {"number": 2, "repo": "mqucifer/crew"},
            "blocks": ["refused", "landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "retried",
        },
    ]
    cards = [
        {
            "number": i,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": f"story-{i}.py",
        }
        for i in range(1, 3)
    ]
    _make_package_first_attempt(
        tag,
        numerator=2,
        denominator=2,
        stories=stories,
        cards=cards,
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # The retried story's row must not show 'first try'
        row_2 = re.search(
            r'row.*?#2.*?attempt-status.*?>(.*?)</span>', html, re.DOTALL
        )
        assert row_2, "row for story #2 not found"
        status_text = row_2.group(1)
        assert "first try" not in status_text, (
            f"retried story shows 'first try', expected a different badge; got {status_text!r}"
        )
        assert "retried" in status_text, (
            f"retried story should show 'retried', got {status_text!r}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_no_cutting_to_denominator():
    """AC2: 5 stories with events in a sprint render 5 attempt-row elements
    even when first_attempt_denominator is 3."""
    tag = "delivery-history-TEST"
    stories = [
        {
            "card": {"number": i, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "first_try",
        }
        for i in range(1, 6)
    ]
    cards = [
        {
            "number": i,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": f"story-{i}.py",
        }
        for i in range(1, 6)
    ]
    _make_package_first_attempt(
        tag,
        numerator=3,
        denominator=3,
        stories=stories,
        cards=cards,
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        row_count = html.count('class="attempt-row"')
        assert row_count == 5, (
            f"expected exactly 5 attempt-row elements, found {row_count}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_first_try_pattern_shows_first_try_regardless_of_position():
    """AC3: a story with pattern 'first_try' that appears after position
    first_attempt_numerator still displays 'first try'."""
    tag = "delivery-history-TEST"
    # Story 1: retried (position 1, within numerator)
    # Story 2: first_try (position 2, beyond numerator=1)
    stories = [
        {
            "card": {"number": 1, "repo": "mqucifer/crew"},
            "blocks": ["refused", "landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "retried",
        },
        {
            "card": {"number": 2, "repo": "mqucifer/crew"},
            "blocks": ["landed"],
            "crew_fixes": [],
            "delivered": True,
            "pattern": "first_try",
        },
    ]
    cards = [
        {
            "number": i,
            "repo": "mqucifer/crew",
            "sprint": "Sprint 6",
            "title": f"story-{i}.py",
        }
        for i in range(1, 3)
    ]
    _make_package_first_attempt(
        tag,
        numerator=1,
        denominator=2,
        stories=stories,
        cards=cards,
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        # Story #2 has pattern first_try and must show 'first try'
        row_2 = re.search(
            r'row.*?#2.*?attempt-status.*?>(.*?)</span>', html, re.DOTALL
        )
        assert row_2, "row for story #2 not found"
        status_text = row_2.group(1)
        assert status_text == "first try", (
            f"story with pattern first_try should show 'first try', got {status_text!r}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_stats_wrap_to_multiple_rows_at_phone_width():
    """AC1: at a 375px viewport the .stats container is taller than a single .stat,
    proving the five stats wrap to at least two rows instead of one."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_minutes": 720,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 375, "height": 812})
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stats")
            stats_height = page.evaluate(
                "document.querySelector('.stats').getBoundingClientRect().height"
            )
            stat_height = page.evaluate(
                "document.querySelector('.stat').getBoundingClientRect().height"
            )
            assert stats_height > stat_height, (
                f"at 375px .stats height {stats_height} is not greater than a "
                f"single .stat height {stat_height}; the stats did not wrap to "
                f"multiple rows"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_stat_values_not_horizontally_clipped_at_phone_width():
    """AC2: at a 375px viewport no .stat__value is horizontally clipped: each one's
    scrollWidth equals its clientWidth."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_minutes": 102,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 375, "height": 812})
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stat__value")
            clipped = page.evaluate(
                """
                () => {
                    const out = [];
                    for (const el of document.querySelectorAll('.stat__value')) {
                        if (el.scrollWidth > el.clientWidth) {
                            out.push(el.textContent.trim());
                        }
                    }
                    return out;
                }
                """
            )
            assert clipped == [], (
                f"at 375px these .stat__value elements are horizontally "
                f"clipped: {clipped}"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_stats_single_row_at_desktop_width():
    """AC3: at a 1440px viewport all five .stat elements share the same top offset,
    i.e. they sit in a single row, unchanged from the desktop layout."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_minutes": 720,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stats")
            tops = page.evaluate(
                """
                () => Array.from(
                    document.querySelectorAll('.stat')
                ).map((el) => el.getBoundingClientRect().top)
                """
            )
            assert len(tops) == 5, f"expected 5 .stat elements, got {len(tops)}"
            assert len(set(tops)) == 1, (
                f"at 1440px the .stat top offsets differ {tops}; the stats are "
                f"not in a single row"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_stat_values_and_order_at_phone_width():
    """AC4: at a 375px viewport the five .stat__value elements keep their document
    order and show the same values as at 1440px for the same package data. The
    reflow changes the layout, not the values or their order.

    Note: the cycle-time stat is rendered by build.py's _format_minutes from
    cycle_time_minutes, which only emits hours/minutes ('N hr M min'); it never
    renders '0.5 days'. So this proves the values and order are preserved
    across viewports (the criterion's intent) rather than pinning a literal
    '0.5 days' the build cannot produce.
    """
    tag = "delivery-history-TEST"
    metrics = {
        "Sprint 6": {
            "throughput": 22,
            "points_delivered": 63,
            "first_attempt_numerator": 12,
            "first_attempt_denominator": 22,
            "escalation_count": 1,
            "cycle_time_minutes": 720,
        }
    }
    _make_fake_package(tag, ["Sprint 6"], metrics=metrics)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright

        def read_values(viewport):
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport=viewport)
                _intercept_design_system(page)
                page.goto(f"file://{page_path}")
                page.wait_for_selector(".stat__value")
                values = page.evaluate(
                    """
                    () => Array.from(
                        document.querySelectorAll('.stat__value')
                    ).map((el) => el.textContent.trim())
                    """
                )
                browser.close()
            return values

        phone = read_values({"width": 375, "height": 812})
        desktop = read_values({"width": 1440, "height": 900})
        assert len(phone) == 5, f"expected 5 .stat__value at 375px, got {phone}"
        assert len(desktop) == 5, f"expected 5 .stat__value at 1440px, got {desktop}"
        assert phone == desktop, (
            f"the five stat values differ between 375px {phone} and 1440px "
            f"{desktop}; reflow must not change the values or their order"
        )
        # The two fixed endpoints (first and last) pin the order and the
        # throughput/points values the criterion names.
        assert phone[0] == "22", f"first stat value is {phone[0]!r}, expected '22'"
        assert phone[4] == "63", (
            f"last stat value is {phone[4]!r}, expected '63'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_stat_values_at_least_text_xl_at_phone_width():
    """AC5: at a 375px viewport every .stat__value keeps a computed font-size of at
    least 24px (--text-xl); the reflow must not shrink the values to fit the phone."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_minutes": 720,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 375, "height": 812})
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stat__value")
            sizes = page.evaluate(
                """
                () => Array.from(
                    document.querySelectorAll('.stat__value')
                ).map(
                    (el) =>
                        parseFloat(
                            getComputedStyle(el).fontSize
                        )
                )
                """
            )
            assert len(sizes) == 5, f"expected 5 .stat__value, got {len(sizes)}"
            under = [
                (s, i)
                for i, s in enumerate(sizes)
                if s < 24
            ]
            assert under == [], (
                f"at 375px these .stat__value elements are below 24px "
                f"(--text-xl): {under}"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_first_stat_label_visible_under_value_at_phone_width():
    """AC6: at a 375px viewport the .stat__label following the .stat__value whose
    text is '22' reads exactly 'stories delivered' and is not horizontally clipped
    (scrollWidth == clientWidth)."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_minutes": 720,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 375, "height": 812})
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stat__value")
            result = page.evaluate(
                """
                () => {
                    for (const value of document.querySelectorAll(
                        '.stat__value'
                    )) {
                        if (value.textContent.trim() !== '22') {
                            continue;
                        }
                        const label = value.nextElementSibling;
                        if (!label || !label.classList.contains('stat__label')) {
                            return { error: 'no .stat__label follows the 22 value' };
                        }
                        return {
                            text: label.textContent.trim(),
                            clipped: label.scrollWidth > label.clientWidth,
                        };
                    }
                    return { error: 'no .stat__value with text 22' };
                }
                """
            )
            assert "error" not in result, f"AC6 lookup failed: {result}"
            assert result["text"] == "stories delivered", (
                f"the label under the '22' value is {result['text']!r}, expected "
                f"'stories delivered'"
            )
            assert result["clipped"] is False, (
                f"the 'stories delivered' label is horizontally clipped at 375px "
                f"(scrollWidth > clientWidth)"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_stats_single_row_height_at_desktop_width():
    """AC7: at a 1440px viewport all five .stat elements share the same top offset
    and the .stats element's height equals a single .stat's height — a single row,
    unchanged from the desktop layout."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 22,
                "points_delivered": 63,
                "first_attempt_numerator": 12,
                "first_attempt_denominator": 22,
                "escalation_count": 1,
                "cycle_time_minutes": 720,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_selector(".stats")
            tops = page.evaluate(
                """
                () => Array.from(
                    document.querySelectorAll('.stat')
                ).map((el) => el.getBoundingClientRect().top)
                """
            )
            assert len(tops) == 5, f"expected 5 .stat elements, got {len(tops)}"
            assert len(set(tops)) == 1, (
                f"at 1440px the .stat top offsets differ {tops}; not a single row"
            )
            stats_height = page.evaluate(
                "document.querySelector('.stats').getBoundingClientRect().height"
            )
            stat_height = page.evaluate(
                "document.querySelector('.stat').getBoundingClientRect().height"
            )
            assert stats_height == stat_height, (
                f"at 1440px .stats height {stats_height} differs from a single "
                f".stat height {stat_height}; the stats are not a single row"
            )
            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_view_nav_links_at_least_44px_at_phone_width():
    """AC1: every <a> in nav.nav has a bounding-box height >= 44px at 375px."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            heights = page.evaluate(
                "Array.from(document.querySelectorAll('nav.nav a'))"
                ".map(el => el.getBoundingClientRect().height)"
            )
            assert len(heights) == 3, (
                f"expected 3 view-nav links, got {len(heights)}"
            )
            for h in heights:
                assert h >= 44, f"view-nav link height {h} < 44px"

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_nav_links_at_least_44px_at_phone_width():
    """AC2: every <a> in the sprint nav has a bounding-box height >= 44px at 375px."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag, ["Sprint 5", "Sprint 6", "Sprint 7"])
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            heights = page.evaluate(
                "Array.from(document.querySelectorAll(\"nav[aria-label='Sprints'] a\"))"
                ".map(el => el.getBoundingClientRect().height)"
            )
            assert len(heights) == 3, (
                f"expected 3 sprint-nav links, got {len(heights)}"
            )
            for h in heights:
                assert h >= 44, f"sprint-nav link height {h} < 44px"

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_view_nav_no_horizontal_overflow_at_phone_width():
    """AC3: nav.nav scrollWidth equals clientWidth at 375px (no horizontal overflow)."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag, ["Sprint 6"])
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            scroll_width = page.evaluate("document.querySelector('nav.nav').scrollWidth")
            client_width = page.evaluate("document.querySelector('nav.nav').clientWidth")
            assert scroll_width == client_width, (
                f"nav.nav scrollWidth {scroll_width} != clientWidth {client_width}: "
                "links cause horizontal overflow at phone width"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_view_nav_exactly_three_links_in_order_at_phone_width():
    """AC4: at 375px, nav.nav has exactly 3 links 'Sprint', "A story's journey", 'Replay'."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag, ["Sprint 6"])
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            texts = page.evaluate(
                "Array.from(document.querySelectorAll('nav.nav a'))"
                ".map(el => el.textContent.trim())"
            )
            assert texts == ["Sprint", "A story's journey", "Replay"], (
                f"view-nav links are {texts}, expected the desktop set and order"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_view_nav_current_page_is_sprint_at_phone_width():
    """AC5: at 375px, the nav.nav link with aria-current=page has text 'Sprint'."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag, ["Sprint 6"])
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            text = page.evaluate(
                "document.querySelector(\"nav.nav a[aria-current='page']\")"
                ".textContent.trim()"
            )
            assert text == "Sprint", (
                f"aria-current page link text is {text!r}, expected 'Sprint'"
            )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_view_nav_links_at_least_40px_at_desktop_width():
    """AC6: at 1440px, every <a> in nav.nav has a bounding-box height >= 40px."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag, ["Sprint 6"])
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            heights = page.evaluate(
                "Array.from(document.querySelectorAll('nav.nav a'))"
                ".map(el => el.getBoundingClientRect().height)"
            )
            assert len(heights) == 3, (
                f"expected 3 view-nav links, got {len(heights)}"
            )
            for h in heights:
                assert h >= 40, f"view-nav link height {h} < 40px on desktop"

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_nav_links_visible_with_sprint_names_at_phone_width():
    """AC7: at 375px, sprint-nav links carry sprint names and none is display:none or hidden."""
    tag = "delivery-history-TEST"
    names = ["Sprint 5", "Sprint 6", "Sprint 7"]
    _make_fake_package(tag, names)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = (BUILD_DIR / "sprint-6.html").resolve()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            _intercept_design_system(page)
            page.goto(f"file://{page_path}")
            page.wait_for_load_state("domcontentloaded")

            states = page.evaluate(
                "Array.from(document.querySelectorAll(\"nav[aria-label='Sprints'] a\"))"
                ".map(el => { const cs = getComputedStyle(el); "
                "return { text: el.textContent.trim(), display: cs.display, "
                "visibility: cs.visibility }; })"
            )
            assert len(states) == 3, (
                f"expected 3 sprint-nav links, got {len(states)}"
            )
            for i, s in enumerate(states):
                assert names[i] in s["text"], (
                    f"sprint-nav link {i} text {s['text']!r} does not contain {names[i]!r}"
                )
                assert s["display"] != "none", (
                    f"sprint-nav link {s['text']!r} has display:none"
                )
                assert s["visibility"] != "hidden", (
                    f"sprint-nav link {s['text']!r} has visibility:hidden"
                )

            browser.close()
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_first_attempt_rate_label():
    """AC1, AC3: first_attempt_rate_percent renders as 'first-attempt rate:' in .changed-trend-values."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 7",
        [
            {
                "text": "First-attempt rate rose",
                "measure": "first_attempt_rate_percent",
                "previous": 40,
                "now": 55,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        values_div = re.search(
            r'class="changed-trend-values">(.*?)</div>', html, re.DOTALL
        )
        assert values_div, "no changed-trend-values div found"
        values_text = values_div.group(0)
        assert "first-attempt rate:" in values_text, (
            f"expected 'first-attempt rate:' in .changed-trend-values, got: {values_text!r}"
        )
        assert "first_attempt_rate_percent" not in values_text, (
            f"raw field name 'first_attempt_rate_percent' still present in .changed-trend-values"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_escalation_count_label():
    """AC2, AC4: escalation_count renders as 'escalations:' in .changed-trend-values."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 7",
        [
            {
                "text": "Escalations held steady",
                "measure": "escalation_count",
                "previous": 2,
                "now": 0,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        values_div = re.search(
            r'class="changed-trend-values">(.*?)</div>', html, re.DOTALL
        )
        assert values_div, "no changed-trend-values div found"
        values_text = values_div.group(0)
        assert "escalations:" in values_text, (
            f"expected 'escalations:' in .changed-trend-values, got: {values_text!r}"
        )
        assert "escalation_count" not in values_text, (
            f"raw field name 'escalation_count' still present in .changed-trend-values"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_points_delivered_label():
    """AC5: points_delivered renders as 'points delivered:' in .changed-trend-values."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 7",
        [
            {
                "text": "Points delivered up",
                "measure": "points_delivered",
                "previous": 40,
                "now": 63,
                "better": True,
                "source": "sprint-metrics",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-7.html").read_text()
        values_div = re.search(
            r'class="changed-trend-values">(.*?)</div>', html, re.DOTALL
        )
        assert values_div, "no changed-trend-values div found"
        values_text = values_div.group(0)
        assert "points delivered:" in values_text, (
            f"expected 'points delivered:' in .changed-trend-values, got: {values_text!r}"
        )
        assert "points_delivered" not in values_text, (
            f"raw field name 'points_delivered' still present in .changed-trend-values"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_no_field_name_pattern_in_values():
    """AC6: no .changed-trend-values element contains a substring matching [a-z]+_[a-z]+."""
    tag = "delivery-history-TEST"
    _make_package_with_changed(
        tag,
        "Sprint 8",
        [
            {
                "text": "First-attempt rate rose",
                "measure": "first_attempt_rate_percent",
                "previous": 40,
                "now": 55,
                "better": True,
                "source": "sprint-metrics",
            },
            {
                "text": "Escalations dropped",
                "measure": "escalation_count",
                "previous": 2,
                "now": 0,
                "better": True,
                "source": "sprint-metrics",
            },
            {
                "text": "Points delivered up",
                "measure": "points_delivered",
                "previous": 40,
                "now": 63,
                "better": True,
                "source": "sprint-metrics",
            },
            {
                "text": "Stories delivered up",
                "measure": "throughput",
                "previous": 1,
                "now": 12,
                "better": True,
                "source": "sprint-metrics",
            },
            {
                "text": "Days blocked down",
                "measure": "blocked_aging_days",
                "previous": 1,
                "now": 0,
                "better": True,
                "source": "sprint-metrics",
            },
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-8.html").read_text()
        values_divs = re.findall(
            r'class="changed-trend-values">(.*?)</div>', html, re.DOTALL
        )
        assert len(values_divs) == 5, (
            f"expected 5 .changed-trend-values elements, got {len(values_divs)}"
        )
        field_name_pattern = re.compile(r"[a-z]+_[a-z]+")
        for i, div_text in enumerate(values_divs, 1):
            match = field_name_pattern.search(div_text)
            assert match is None, (
                f".changed-trend-values #{i} contains field-name pattern "
                f"{match.group()!r}: {div_text!r}"
            )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_label_test_assertion_failed():
    """AC1: code 'test_assertion_failed' renders as exactly 'A test's assertion failed' in the label span."""
    tag = "delivery-history-TEST"
    causes = [{"reason": "test_assertion_failed", "count": 10}]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # The label span is the only span in the row without a class attribute;
        # the count span carries class="num". Extract its exact text content.
        match = re.search(r"<span>(.*?)</span>", section)
        assert match is not None, "no label span found in the cause-chart"
        assert match.group(1) == "A test's assertion failed", (
            f"label span text is {match.group(1)!r}, "
            "expected 'A test's assertion failed'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_label_already_exists():
    """AC2: code 'already_exists' renders as '"already exists"' in the label span."""
    tag = "delivery-history-TEST"
    causes = [{"reason": "already_exists", "count": 6}]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        assert '>"already exists"</span>' in section, (
            "cause label should be '\"already exists\"'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_label_must_create_or_edit_file():
    """AC3 (UX): code 'must_create_or_edit_file' renders as 'Must create or edit a file'."""
    tag = "delivery-history-TEST"
    causes = [{"reason": "must_create_or_edit_file", "count": 3}]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        assert ">Must create or edit a file</span>" in section, (
            "cause label should be 'Must create or edit a file'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_labels_no_raw_code_pattern():
    """AC4 (UX): no label span in the cause-chart contains a raw code pattern [a-z]+_[a-z]+."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "test_assertion_failed", "count": 10},
        {"reason": "already_exists", "count": 6},
        {"reason": "must_create_or_edit_file", "count": 3},
        {"reason": "undefined_name", "count": 2},
        {"reason": "no_test_written", "count": 2},
        {"reason": "unrecorded", "count": 2},
    ]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # Extract all span elements; label spans are those without class="num
        all_spans = re.findall(r"<span([^>]*)>(.*?)</span>", section)
        label_texts = [
            text for attrs, text in all_spans if 'class="num' not in attrs
        ]
        assert len(label_texts) == 6, f"expected 6 label spans, got {len(label_texts)}"
        for text in label_texts:
            assert not re.search(r"[a-z]+_[a-z]+", text), (
                f"label span contains raw code pattern: {text!r}"
            )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_label_review_renders_as_cause_not_recorded():
    """AC1: code 'REVIEW' (not in CAUSE_LABELS) renders as 'Cause not recorded', not 'REVIEW'."""
    tag = "delivery-history-TEST"
    causes = [{"reason": "REVIEW", "count": 1}]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # The label span must contain 'Cause not recorded'
        assert ">Cause not recorded</span>" in section, (
            "label span should read 'Cause not recorded' for unknown code 'REVIEW'"
        )
        # The raw code 'REVIEW' must not appear in a label span
        assert ">REVIEW</span>" not in section, (
            "raw code 'REVIEW' must not appear as a label"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_cause_label_qa_renders_as_cause_not_recorded():
    """AC2: code 'QA' (not in CAUSE_LABELS) renders as 'Cause not recorded', not 'QA'."""
    tag = "delivery-history-TEST"
    causes = [{"reason": "QA", "count": 1}]
    _make_fake_package(
        tag,
        ["Sprint 6"],
        metrics={
            "Sprint 6": {
                "throughput": 5,
                "points_delivered": 10,
                "first_attempt_numerator": 3,
                "first_attempt_denominator": 5,
                "escalation_count": 0,
                "cycle_time_days": 2.0,
                "top_failure_causes": causes,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-6.html").read_text()
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # The label span must contain 'Cause not recorded'
        assert ">Cause not recorded</span>" in section, (
            "label span should read 'Cause not recorded' for unknown code 'QA'"
        )
        # The raw code 'QA' must not appear in a label span
        assert ">QA</span>" not in section, (
            "raw code 'QA' must not appear as a label"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_header_shows_most_recent_sprint():
    """AC1: h1 is the most recent sprint name; body contains the date range."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 5", "start": "2026-09-15", "end": "2026-09-29"},
        {"name": "Sprint 6", "start": "2026-09-29", "end": "2026-10-06"},
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    _make_fake_package(tag, sprints=sprints)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        h1_match = re.search(r"<h1>(.*?)</h1>", html)
        assert h1_match, "no <h1> element found"
        assert h1_match.group(1) == "Sprint 7", f"h1 is {h1_match.group(1)!r}"
        assert "2026-10-07 – 2026-10-13" in html, "date range not found in page"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_structural_containers_empty():
    """AC2: Timeline, Who, and Event ticker sections exist and are empty."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        timeline_match = re.search(
            r'<section[^>]*aria-label="Timeline"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert timeline_match, "no section with aria-label='Timeline'"
        assert timeline_match.group(1).strip() == "", (
            f"Timeline has children: {timeline_match.group(1).strip()!r}"
        )
        who_match = re.search(
            r'<(?:section|aside)[^>]*aria-label="[^"]*Who[^"]*"[^>]*>(.*?)</(?:section|aside)>',
            html, re.DOTALL,
        )
        assert who_match, "no section/aside with aria-label containing 'Who'"
        assert who_match.group(1).strip() == "", (
            f"Who section has children: {who_match.group(1).strip()!r}"
        )
        ticker_match = re.search(
            r'<section[^>]*aria-label="Event ticker"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert ticker_match, "no section with aria-label='Event ticker'"
        assert ticker_match.group(1).strip() == "", (
            f"Event ticker has children: {ticker_match.group(1).strip()!r}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_nav_aria_current():
    """AC3: Replay link has aria-current='page'; Sprint and journey links do not."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        view_nav = _view_nav(html)
        links = re.findall(r"<a[^>]*>(.*?)</a>", view_nav)
        assert "Replay" in links, f"view nav links: {links}"
        replay_link = re.search(
            r'<a[^>]*aria-current="page"[^>]*>Replay</a>', view_nav
        )
        assert replay_link, "Replay link does not have aria-current='page'"
        for text in ("Sprint", "A story's journey"):
            link_match = re.search(
                rf'<a[^>]*>{re.escape(text)}</a>', view_nav
            )
            assert link_match, f"link for {text!r} not found"
            assert "aria-current" not in link_match.group(0), (
                f"link {text!r} should not have aria-current"
            )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_single_sprint_header():
    """AC4: single sprint 'Sprint 1' shows correct h1 and date range."""
    tag = "delivery-history-TEST"
    sprints = [{"name": "Sprint 1", "start": "2026-09-01", "end": "2026-09-07"}]
    _make_fake_package(tag, sprints=sprints)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        h1_match = re.search(r"<h1>(.*?)</h1>", html)
        assert h1_match, "no <h1> element found"
        assert h1_match.group(1) == "Sprint 1", f"h1 is {h1_match.group(1)!r}"
        assert "2026-09-01 – 2026-09-07" in html, "date range not found"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_no_periods_board_empty():
    """AC5: no periods for most recent sprint, board has 0 columns, containers exist."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 6", "start": "2026-09-29", "end": "2026-10-06"},
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    _make_fake_package(tag, sprints=sprints)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        h1_match = re.search(r"<h1>(.*?)</h1>", html)
        assert h1_match and "Sprint 7" in h1_match.group(1), (
            f"h1 is {h1_match.group(1) if h1_match else 'MISSING'!r}"
        )
        assert 'aria-label="Timeline"' in html, "Timeline not found"
        assert 'aria-label="Event ticker"' in html, "Event ticker not found"
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        cols = re.findall(r'class="replay-col"', board_match.group(1))
        assert len(cols) == 0, f"Board has {len(cols)} columns, expected 0"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_body_element_order():
    """AC6: Timeline before Board before Who before Event ticker in source order."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        timeline_pos = html.find('aria-label="Timeline"')
        board_pos = html.find('aria-label="Board"')
        who_pos = html.find('aria-label="Who')
        ticker_pos = html.find('aria-label="Event ticker"')
        assert timeline_pos != -1, "Timeline not found"
        assert board_pos != -1, "Board not found"
        assert who_pos != -1, "Who not found"
        assert ticker_pos != -1, "Event ticker not found"
        assert timeline_pos < board_pos, "Timeline should appear before Board"
        assert board_pos < who_pos, "Board should appear before Who"
        assert who_pos < ticker_pos, "Who should appear before Event ticker"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_board_aria_label_no_placeholder():
    """AC7: Board section has aria-label='Board' and no 'placeholder' text."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        assert "placeholder" not in board_match.group(1).lower(), (
            "Board section contains 'placeholder' text"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_no_periods_zero_cols_and_empty_timeline():
    """AC8: single sprint with no periods, 0 .replay-col in Board, 0 children in Timeline."""
    tag = "delivery-history-TEST"
    sprints = [{"name": "Sprint 1", "start": "2026-09-01", "end": "2026-09-07"}]
    _make_fake_package(tag, sprints=sprints)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        cols = re.findall(r'class="replay-col"', board_match.group(1))
        assert len(cols) == 0, f"Board has {len(cols)} .replay-col elements, expected 0"
        timeline_match = re.search(
            r'<section[^>]*aria-label="Timeline"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert timeline_match, "no Timeline section"
        assert timeline_match.group(1).strip() == "", (
            f"Timeline has children: {timeline_match.group(1).strip()!r}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_board_columns_from_events_in_tone_order():
    """AC1: events with from/to columns Sprint Backlog, In Progress, Done render 3 columns in tone order."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 6", "start": "2026-09-29", "end": "2026-10-06"},
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"at": "2026-10-07T09:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress"},
        {"at": "2026-10-07T14:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "In Progress", "to_column": "Done"},
    ]
    cards = [
        {"number": 1, "repo": "mqucifer/crew", "title": "test.py", "url": "https://github.com/mqucifer/crew-presentation/issues/1"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        headers = re.findall(
            r'class="replay-col__header">(.*?)<', board_match.group(1)
        )
        assert len(headers) == 3, f"Expected 3 columns, got {len(headers)}: {headers}"
        assert headers == ["Sprint Backlog", "In Progress", "Done"], (
            f"Column order is {headers}, expected ['Sprint Backlog', 'In Progress', 'Done']"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_card_initial_column_is_earliest_from_column():
    """AC2: card 127 with earliest event from_column 'Sprint Backlog' is in that column only."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"at": "2026-10-07T09:00:00Z", "card": {"number": 127, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress"},
        {"at": "2026-10-07T14:00:00Z", "card": {"number": 127, "repo": "mqucifer/crew"}, "from_column": "In Progress", "to_column": "Done"},
    ]
    cards = [
        {"number": 127, "repo": "mqucifer/crew", "title": "thresholds.py", "url": "https://github.com/mqucifer/crew-presentation/issues/127"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        card_text = "[mqucifer/crew-presentation#127](https://github.com/mqucifer/crew-presentation/issues/127)"
        sb_col_match = re.search(
            r'class="replay-col__header">Sprint Backlog</div>\s*<div class="replay-col__cards">(.*?)</div>\s*</div>',
            board_match.group(1), re.DOTALL
        )
        assert sb_col_match, "Sprint Backlog column not found"
        assert card_text in sb_col_match.group(1), (
            f"Card 127 not in Sprint Backlog column"
        )
        ip_col_match = re.search(
            r'class="replay-col__header">In Progress</div>\s*<div class="replay-col__cards">(.*?)</div>\s*</div>',
            board_match.group(1), re.DOTALL
        )
        if ip_col_match:
            assert card_text not in ip_col_match.group(1), (
                "Card 127 incorrectly in In Progress column"
            )
        done_col_match = re.search(
            r'class="replay-col__header">Done</div>\s*<div class="replay-col__cards">(.*?)</div>\s*</div>',
            board_match.group(1), re.DOTALL
        )
        if done_col_match:
            assert card_text not in done_col_match.group(1), (
                "Card 127 incorrectly in Done column"
            )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_card_text_includes_link_and_title():
    """AC3: card's visible text includes the exact link string and the card's title."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"at": "2026-10-07T09:00:00Z", "card": {"number": 127, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress"},
    ]
    cards = [
        {"number": 127, "repo": "mqucifer/crew", "title": "thresholds.py", "url": "https://github.com/mqucifer/crew-presentation/issues/127"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        card_text = "[mqucifer/crew-presentation#127](https://github.com/mqucifer/crew-presentation/issues/127)"
        found = False
        for m in re.finditer(r'<div class="replay-card">(.*?)</div>', board_match.group(1), re.DOTALL):
            content = m.group(1)
            if card_text in content:
                found = True
                assert "thresholds.py" in content, (
                    f"Card title 'thresholds.py' not found in card element: {content!r}"
                )
                break
        assert found, f"Card with link {card_text!r} not found in board"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_card_without_events_not_on_board():
    """AC4: card 99 in cards array but no events for it → not rendered on board."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"at": "2026-10-07T09:00:00Z", "card": {"number": 127, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress"},
    ]
    cards = [
        {"number": 127, "repo": "mqucifer/crew", "title": "thresholds.py", "url": "https://github.com/mqucifer/crew-presentation/issues/127"},
        {"number": 99, "repo": "mqucifer/crew", "title": "other.py", "url": "https://github.com/mqucifer/crew-presentation/issues/99"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        card_99_text = "[mqucifer/crew-presentation#99](https://github.com/mqucifer/crew-presentation/issues/99)"
        assert card_99_text not in board_match.group(1), (
            f"Card 99 should not be on the board but was found"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_board_single_column_when_all_events_same_column():
    """AC5: 4 events all from Sprint Backlog to Sprint Backlog → exactly 1 column."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"at": "2026-10-07T08:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "Sprint Backlog"},
        {"at": "2026-10-07T09:00:00Z", "card": {"number": 2, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "Sprint Backlog"},
        {"at": "2026-10-07T10:00:00Z", "card": {"number": 3, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "Sprint Backlog"},
        {"at": "2026-10-07T11:00:00Z", "card": {"number": 4, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "Sprint Backlog"},
    ]
    cards = [
        {"number": 1, "repo": "mqucifer/crew", "title": "a.py", "url": "https://github.com/mqucifer/crew-presentation/issues/1"},
        {"number": 2, "repo": "mqucifer/crew", "title": "b.py", "url": "https://github.com/mqucifer/crew-presentation/issues/2"},
        {"number": 3, "repo": "mqucifer/crew", "title": "c.py", "url": "https://github.com/mqucifer/crew-presentation/issues/3"},
        {"number": 4, "repo": "mqucifer/crew", "title": "d.py", "url": "https://github.com/mqucifer/crew-presentation/issues/4"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        headers = re.findall(
            r'class="replay-col__header">(.*?)<', board_match.group(1)
        )
        assert len(headers) == 1, f"Expected 1 column, got {len(headers)}: {headers}"
        assert headers[0] == "Sprint Backlog", f"Column is {headers[0]!r}, expected 'Sprint Backlog'"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_done_column_present_but_empty():
    """AC6: events with to_column Done but no from_column Done → Done column exists with 0 cards."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"at": "2026-10-07T09:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress"},
        {"at": "2026-10-07T14:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "In Progress", "to_column": "Done"},
    ]
    cards = [
        {"number": 1, "repo": "mqucifer/crew", "title": "test.py", "url": "https://github.com/mqucifer/crew-presentation/issues/1"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        done_match = re.search(
            r'class="replay-col__header">Done</div>\s*<div class="replay-col__cards">(.*?)</div>',
            board_match.group(1), re.DOTALL
        )
        assert done_match, "Done column not found"
        cards_in_done = re.findall(r'class="replay-card"', done_match.group(1))
        assert len(cards_in_done) == 0, (
            f"Done column has {len(cards_in_done)} cards, expected 0"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_single_event_card_in_from_column_with_num_class():
    """AC7: card 130 with single event from Sprint Backlog → in that column, shows title, link in .num element."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"at": "2026-10-07T08:00:00Z", "card": {"number": 130, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress"},
    ]
    cards = [
        {"number": 130, "repo": "mqucifer/crew", "title": "serve.py", "url": "https://github.com/mqucifer/crew-presentation/issues/130"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        card_text = "[mqucifer/crew-presentation#130](https://github.com/mqucifer/crew-presentation/issues/130)"
        sb_col_match = re.search(
            r'class="replay-col__header">Sprint Backlog</div>\s*<div class="replay-col__cards">(.*?)</div>\s*</div>',
            board_match.group(1), re.DOTALL
        )
        assert sb_col_match, "Sprint Backlog column not found"
        assert card_text in sb_col_match.group(1), (
            "Card 130 not in Sprint Backlog column"
        )
        assert "serve.py" in sb_col_match.group(1), (
            "Card title 'serve.py' not found"
        )
        num_match = re.search(
            r'<(\w+)[^>]*class="[^"]*num[^"]*"[^>]*>([^<]*)</\1>',
            sb_col_match.group(1)
        )
        assert num_match, "No element with class 'num' found in Sprint Backlog column"
        assert card_text in num_match.group(2), (
            f"Link text not inside .num element: {num_match.group(2)!r}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_board_four_columns_in_tone_order():
    """AC8: events with Sprint Backlog, In Progress, QAing, Merging → 4 columns in tone order."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"at": "2026-10-07T08:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress"},
        {"at": "2026-10-07T09:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "In Progress", "to_column": "QAing"},
        {"at": "2026-10-07T10:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "QAing", "to_column": "Merging"},
    ]
    cards = [
        {"number": 1, "repo": "mqucifer/crew", "title": "test.py", "url": "https://github.com/mqucifer/crew-presentation/issues/1"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        board_match = re.search(
            r'<section[^>]*aria-label="Board"[^>]*>(.*?)</section>', html, re.DOTALL
        )
        assert board_match, "no Board section"
        headers = re.findall(
            r'class="replay-col__header">(.*?)<', board_match.group(1)
        )
        assert len(headers) == 4, f"Expected 4 columns, got {len(headers)}: {headers}"
        assert headers == ["Sprint Backlog", "In Progress", "QAing", "Merging"], (
            f"Column order is {headers}, expected ['Sprint Backlog', 'In Progress', 'QAing', 'Merging']"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _make_package_with_board(
    tag: str,
    sprints: list[dict],
    events: list[dict],
    cards: list[dict],
    sprint_name: str,
) -> Path:
    """Create a fake package with events for the board tests."""
    metrics = {
        name: {
            "throughput": 5,
            "points_delivered": 10,
            "first_attempt_numerator": 1,
            "first_attempt_denominator": 5,
            "escalation_count": 0,
            "cycle_time_days": 2.0,
        }
        for name in [s["name"] for s in sprints]
    }
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
    events_file_name = f"events/sprint-{sprint_name.lower().replace(' ', '-')}.json"
    (pkg_dir / "events").mkdir(exist_ok=True)
    (pkg_dir / events_file_name).write_text(json.dumps({"events": events}))
    index = {
        "sprints": sprints,
        "cards": cards,
        "crew_repository": "mqucifer/crew",
        "sprint_metrics": {"answers": metrics},
        "periods": [
            {"sprint": sprint_name, "file": events_file_name}
        ],
    }
    (pkg_dir / "delivery-history.json").write_text(json.dumps(index))
    return pkg_dir


def _extract_replay_data(html: str) -> dict:
    """Extract and parse the replay-data JSON from the replay.html."""
    match = re.search(
        r'<script type="application/json" id="replay-data">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match, "no replay-data script element found"
    return json.loads(match.group(1))


def test_replay_json_has_sprint_events_and_cards():
    """AC1: parsed JSON has sprint name, events array of length 5, and cards array."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"kind": "move", "at": "2026-10-07T08:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress", "role": "Developer"},
        {"kind": "move", "at": "2026-10-07T09:00:00Z", "card": {"number": 2, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress", "role": "Developer"},
        {"kind": "move", "at": "2026-10-08T10:00:00Z", "card": {"number": 3, "repo": "mqucifer/crew"}, "from_column": "In Progress", "to_column": "Reviewing", "role": "Developer"},
        {"kind": "move", "at": "2026-10-09T11:00:00Z", "card": {"number": 4, "repo": "mqucifer/crew"}, "from_column": "Reviewing", "to_column": "QAing", "role": "QA Engineer"},
        {"kind": "move", "at": "2026-10-10T12:00:00Z", "card": {"number": 5, "repo": "mqucifer/crew"}, "from_column": "QAing", "to_column": "Done", "role": "QA Engineer"},
    ]
    cards = [
        {"number": 1, "repo": "mqucifer/crew", "title": "alpha"},
        {"number": 2, "repo": "mqucifer/crew", "title": "beta"},
        {"number": 3, "repo": "mqucifer/crew", "title": "gamma"},
        {"number": 4, "repo": "mqucifer/crew", "title": "delta"},
        {"number": 5, "repo": "mqucifer/crew", "title": "epsilon"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        data = _extract_replay_data(html)
        assert data["sprint"] == "Sprint 7"
        assert isinstance(data["events"], list)
        assert len(data["events"]) == 5
        assert isinstance(data["cards"], list)
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_json_event_structure_move():
    """AC2: events array contains a move event with card, from_column, to_column, role."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"kind": "move", "at": "2026-10-07T09:00:00Z", "card": {"number": 127, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress", "role": "Developer"},
    ]
    cards = [
        {"number": 127, "repo": "mqucifer/crew", "title": "thresholds.py"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        data = _extract_replay_data(html)
        target = next(e for e in data["events"] if e["card"]["number"] == 127)
        assert target["at"] == "2026-10-07T09:00:00Z"
        assert target["card"]["number"] == 127
        assert target["from_column"] == "Sprint Backlog"
        assert target["to_column"] == "In Progress"
        assert target["role"] == "Developer"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_json_cards_contain_referenced_card():
    """AC3: cards array contains the referenced card with number, repo, title."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"kind": "move", "at": "2026-10-07T09:00:00Z", "card": {"number": 127, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress", "role": "Developer"},
    ]
    cards = [
        {"number": 127, "repo": "mqucifer/crew", "title": "thresholds.py"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        data = _extract_replay_data(html)
        target = next(c for c in data["cards"] if c["number"] == 127)
        assert target["repo"] == "mqucifer/crew"
        assert target["title"] == "thresholds.py"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_json_cards_unknown_card_empty_title():
    """AC4: a card referenced by events but absent from the package gets empty title."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"kind": "move", "at": "2026-10-07T09:00:00Z", "card": {"number": 500, "repo": "other/repo"}, "from_column": "Sprint Backlog", "to_column": "In Progress", "role": "Developer"},
    ]
    cards = [
        {"number": 127, "repo": "mqucifer/crew", "title": "thresholds.py"},
    ]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        data = _extract_replay_data(html)
        target = next(c for c in data["cards"] if c["number"] == 500)
        assert target["repo"] == "other/repo"
        assert target["title"] == ""
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_json_only_most_recent_sprint_events():
    """AC5: events from an older sprint are not present in the JSON."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 5", "start": "2026-09-15", "end": "2026-09-29"},
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    sprint7_events = [
        {"kind": "move", "at": "2026-10-07T09:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress", "role": "Developer"},
    ]
    sprint5_events = [
        {"kind": "move", "at": "2026-09-15T09:00:00Z", "card": {"number": 10, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress", "role": "Developer"},
    ]
    cards = [
        {"number": 1, "repo": "mqucifer/crew", "title": "card-one"},
        {"number": 10, "repo": "mqucifer/crew", "title": "old-card"},
    ]
    metrics = {
        "Sprint 5": {"throughput": 5, "points_delivered": 10, "first_attempt_numerator": 1, "first_attempt_denominator": 5, "escalation_count": 0, "cycle_time_days": 2.0},
        "Sprint 7": {"throughput": 5, "points_delivered": 10, "first_attempt_numerator": 1, "first_attempt_denominator": 5, "escalation_count": 0, "cycle_time_days": 2.0},
    }
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "package": "delivery-history", "date": "2026-01-01"}))
    (pkg_dir / "manifest.schema.json").write_text(json.dumps({"type": "object", "required": ["schema_version"]}))
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object", "required": ["sprints"], "properties": {"sprints": {"type": "array"}}}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events").mkdir(exist_ok=True)
    (pkg_dir / "events/sprint-sprint-7.json").write_text(json.dumps({"events": sprint7_events}))
    (pkg_dir / "events/sprint-sprint-5.json").write_text(json.dumps({"events": sprint5_events}))
    index = {
        "sprints": sprints,
        "cards": cards,
        "crew_repository": "mqucifer/crew",
        "sprint_metrics": {"answers": metrics},
        "periods": [
            {"sprint": "Sprint 5", "file": "events/sprint-sprint-5.json"},
            {"sprint": "Sprint 7", "file": "events/sprint-sprint-7.json"},
        ],
    }
    (pkg_dir / "delivery-history.json").write_text(json.dumps(index))
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        data = _extract_replay_data(html)
        assert data["sprint"] == "Sprint 7"
        for event in data["events"]:
            card_num = event.get("card", {}).get("number")
            assert card_num != 10, f"event from Sprint 5 (card 10) should not be present: {event}"
        assert any(e["card"]["number"] == 1 for e in data["events"])
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_h1_matches_json_sprint_key():
    """AC6: the h1 text is identical to the sprint key in the embedded JSON."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"kind": "move", "at": "2026-10-07T09:00:00Z", "card": {"number": 1, "repo": "mqucifer/crew"}, "from_column": "Sprint Backlog", "to_column": "In Progress", "role": "Developer"},
    ]
    cards = [{"number": 1, "repo": "mqucifer/crew", "title": "card-one"}]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        h1_match = re.search(r"<h1>(.*?)</h1>", html)
        assert h1_match, "no h1 found"
        h1_text = h1_match.group(1)
        data = _extract_replay_data(html)
        assert h1_text == data["sprint"], f"h1={h1_text!r} != sprint={data['sprint']!r}"
        assert data["sprint"] == "Sprint 7"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_json_merge_event_structure():
    """AC7: events array contains a merge event with pull object."""
    tag = "delivery-history-TEST"
    sprints = [
        {"name": "Sprint 7", "start": "2026-10-07", "end": "2026-10-13"},
    ]
    events = [
        {"kind": "merge", "at": "2026-10-09T16:30:00Z", "card": {"number": 125, "repo": "mqucifer/crew"}, "to_column": "Done", "role": "QA Engineer", "pull": {"number": 142, "repo": "mqucifer/crew"}},
    ]
    cards = [{"number": 125, "repo": "mqucifer/crew", "title": "replay.js"}]
    _make_package_with_board(tag, sprints, events, cards, "Sprint 7")
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        data = _extract_replay_data(html)
        target = next(e for e in data["events"] if e["kind"] == "merge")
        assert target["at"] == "2026-10-09T16:30:00Z"
        assert target["card"]["number"] == 125
        assert target["to_column"] == "Done"
        assert target["role"] == "QA Engineer"
        assert target["pull"]["number"] == 142
        assert target["pull"]["repo"] == "mqucifer/crew"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_replay_data_script_in_body_with_correct_type():
    """AC8: the replay-data script is in <body>, not <head>, with type='application/json'."""
    tag = "delivery-history-TEST"
    _make_fake_package(tag)
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "replay.html").read_text()
        match = re.search(
            r'<script type="application/json" id="replay-data">', html
        )
        assert match, "no script element with correct type and id found"
        script_pos = match.start()
        head_close = html.find("</head>")
        body_open = html.find("<body")
        assert head_close != -1, "no </head> found"
        assert body_open != -1, "no <body> found"
        assert script_pos > head_close, "script element is in <head>, not <body>"
        assert script_pos > body_open, "script element is before <body>"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def _find_site_css_href(html: str) -> str:
    """Extract the href of the <link rel="stylesheet"> whose href contains site.css."""
    matches = re.findall(
        r'<link\s+rel="stylesheet"\s+href="([^"]*site\.css[^"]*)"', html
    )
    assert matches, "no <link rel='stylesheet'> with 'site.css' in href found"
    return matches[0]


def test_story_page_stylesheet_resolves_to_build_css():
    """AC1: story page's site.css href, resolved relative to the page path, yields css/site.css."""
    from urllib.parse import urljoin

    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 114, "repo": "mqucifer/crew-presentation"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 114,
                "repo": "mqucifer/crew-presentation",
                "sprint": "Sprint 6",
                "title": "test.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = BUILD_DIR / "stories" / "mqucifer-crew-presentation-114.html"
        assert page_path.is_file(), f"story page not found: {page_path}"
        html = page_path.read_text()
        href = _find_site_css_href(html)
        # Resolve relative to the page's own path (stories/mqucifer-crew-presentation-114.html)
        resolved = urljoin("stories/mqucifer-crew-presentation-114.html", href)
        assert resolved == "css/site.css", (
            f"resolved to {resolved!r}, expected 'css/site.css'"
        )
        css_path = BUILD_DIR / "css" / "site.css"
        assert css_path.is_file(), f"build/css/site.css does not exist"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_sprint_page_stylesheet_resolves_to_build_css():
    """AC2: sprint page's site.css href, resolved relative to the page path, yields css/site.css."""
    from urllib.parse import urljoin

    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 1, "repo": "mqucifer/crew"},
                "blocks": ["landed"],
                "crew_fixes": [],
                "delivered": True,
            }
        ],
        cards=[
            {
                "number": 1,
                "repo": "mqucifer/crew",
                "sprint": "Sprint 6",
                "title": "x.py",
            }
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        page_path = BUILD_DIR / "sprint-6.html"
        assert page_path.is_file(), f"sprint page not found: {page_path}"
        html = page_path.read_text()
        href = _find_site_css_href(html)
        # Resolve relative to the page's own path (sprint-6.html)
        resolved = urljoin("sprint-6.html", href)
        assert resolved == "css/site.css", (
            f"resolved to {resolved!r}, expected 'css/site.css'"
        )
        css_path = BUILD_DIR / "css" / "site.css"
        assert css_path.is_file(), f"build/css/site.css does not exist"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_null_sprint_metrics_render_no_none_literal():
    """AC1: null metrics fields render no element containing the text 'None'."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 33"],
        metrics={
            "Sprint 33": {
                "throughput": None,
                "first_attempt_numerator": None,
                "first_attempt_denominator": None,
                "escalation_count": None,
                "points_delivered": None,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-33.html").read_text()
        stats = _stats_section(html)
        values = re.findall(
            r'<span class="stat__value[^"]*">(.*?)</span>', stats, re.DOTALL
        )
        for value in values:
            assert "None" not in value, (
                f"stat value {value!r} contains the programming literal 'None'"
            )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_zero_sprint_metrics_render_zero_and_fraction():
    """AC2: zero metrics render '0' for throughput and '0 of 4' for first try."""
    tag = "delivery-history-TEST"
    _make_fake_package(
        tag,
        ["Sprint 33"],
        metrics={
            "Sprint 33": {
                "throughput": 0,
                "first_attempt_numerator": 0,
                "first_attempt_denominator": 4,
                "escalation_count": 0,
                "points_delivered": 0,
            }
        },
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-33.html").read_text()
        stats = _stats_section(html)
        # '0' immediately before 'stories delivered'
        throughput_match = re.search(
            r'<span class="stat__value[^"]*">\s*([^<]*?)\s*</span>\s*<span class="stat__label">stories delivered</span>',
            stats,
            re.DOTALL,
        )
        assert throughput_match, "no 'stories delivered' stat found"
        assert throughput_match.group(1) == "0", (
            f"throughput stat is {throughput_match.group(1)!r}, expected '0'"
        )
        # '0 of 4' immediately before 'landed first try'
        first_try_match = re.search(
            r'<span class="stat__value[^"]*">\s*([^<]*?)\s*</span>\s*<span class="stat__label">landed first try</span>',
            stats,
            re.DOTALL,
        )
        assert first_try_match, "no 'landed first try' stat found"
        assert first_try_match.group(1) == "0 of 4", (
            f"first-try stat is {first_try_match.group(1)!r}, expected '0 of 4'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)
