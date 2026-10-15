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


def _make_fake_package(
    tag: str,
    sprint_names: list[str] | None = None,
    metrics: dict | None = None,
    sprints: list[dict] | None = None,
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
            assert name in sprint_links, (
                f"'{name}' not in sprint nav links: {sprint_links}"
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
                "cycle_time_days": 3.2,
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
        assert "3.2 days" in stats, f"'3.2 days' not in stats: {stats[:200]}"
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
    """AC7: '3.2 days' is the fourth stat, label 'cycle time', after throughput/first-attempt/escalation."""
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
        assert "3.2 days" in values[3], (
            f"4th stat value is {values[3]!r}, expected to contain '3.2 days'"
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
    metrics = {
        name: {
            "throughput": len(stories),
            "points_delivered": 10,
            "first_attempt_numerator": 1,
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
    """AC4: a story with empty blocks and delivered=false shows a single dashed-border block and 'in progress' in dim text."""
    tag = "delivery-history-TEST"
    _make_package_with_stories(
        tag,
        stories=[
            {
                "card": {"number": 199, "repo": "mqucifer/crew"},
                "blocks": [],
                "crew_fixes": [],
                "delivered": False,
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
        # Status is 'in progress' with the progress class (dim text colour)
        assert 'class="attempt-status attempt-status--progress"' in html, (
            "in-progress status class not found"
        )
        assert ">in progress<" in html, "status text 'in progress' not found"
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
    """AC1: single changed entry renders text, measure, previous, now in reading order."""
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
        pos_text = section_html.index("Cycle time improved")
        pos_measure = section_html.index("cycle_time_days")
        pos_prev = section_html.index("5.2")
        pos_now = section_html.index("3.8")
        assert pos_text < pos_measure < pos_prev < pos_now, (
            f"reading order violated: text@{pos_text}, measure@{pos_measure}, "
            f"prev@{pos_prev}, now@{pos_now}"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_changed_trend_two_entries_in_order():
    """AC2: two changed entries render in package order with correct values."""
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
                "text": "Escalations held steady",
                "measure": "escalation_count",
                "previous": 1,
                "now": 1,
                "better": False,
                "source": "sprint-metrics",
            },
        ],
    )
    original = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")
    try:
        _build()
        html = (BUILD_DIR / "sprint-8.html").read_text()
        entry_count = html.count('class="changed-trend-entry"')
        assert entry_count == 2, f"expected 2 changed-trend entries, got {entry_count}"
        pos_entry1 = html.index("First-attempt rate rose")
        pos_entry2 = html.index("Escalations held steady")
        assert pos_entry1 < pos_entry2, "first entry should appear before second"
        pos_m1 = html.index("first_attempt_rate_percent", pos_entry1)
        pos_p1 = html.index("40", pos_m1)
        pos_n1 = html.index("55", pos_p1)
        assert pos_entry1 < pos_m1 < pos_p1 < pos_n1
        pos_m2 = html.index("escalation_count", pos_entry2)
        second_area = html[pos_m2:]
        num_values = re.findall(r'class="num">(\d+\.?\d*)<', second_area)
        assert num_values[0] == "1", f"expected first value '1', got {num_values[0]!r}"
        assert num_values[1] == "1", f"expected second value '1', got {num_values[1]!r}"
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
    """AC5: previous and now values carry the CSS class 'num'."""
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
        assert 'class="num">5.2<' in html, (
            "previous value 5.2 does not have class 'num'"
        )
        assert 'class="num">3.8<' in html, (
            "now value 3.8 does not have class 'num'"
        )
    finally:
        DELIVERY_HISTORY_TAG.write_text(original)
        shutil.rmtree(PACKAGE_DIR / tag, ignore_errors=True)


def test_failure_causes_four_rows_in_order():
    """AC1: four causes render as four rows in package order with proportional bars."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "A test's assertion failed", "count": 10},
        {"reason": '"already exists"', "count": 6},
        {"reason": "Must create or edit a file", "count": 3},
        {"reason": "Cause not recorded", "count": 2},
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
        section_start = html.index('class="cause-chart"')
        section_end = html.index("</section>", section_start)
        section = html[section_start:section_end]
        # Exactly 4 cause rows
        row_count = section.count('class="cause-row"')
        assert row_count == 4, f"expected 4 cause rows, got {row_count}"
        # Rows in package order
        pos1 = section.index("A test's assertion failed")
        pos2 = section.index('"already exists"')
        pos3 = section.index("Must create or edit a file")
        pos4 = section.index("Cause not recorded")
        assert pos1 < pos2 < pos3 < pos4, "rows not in package order"
        # First bar is longest (100%)
        assert "width:100%" in section, "first bar should be 100% width"
        # Last bar uses unrecorded styling (surface-raised background, dim text)
        assert "cause-bar--unrecorded" in section, "unrecorded bar class missing"
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
    """AC4: section heading is 'Why work didn't land first time' with exactly 4 cause rows."""
    tag = "delivery-history-TEST"
    causes = [
        {"reason": "A test's assertion failed", "count": 10},
        {"reason": '"already exists"', "count": 6},
        {"reason": "Must create or edit a file", "count": 3},
        {"reason": "Cause not recorded", "count": 2},
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
