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
