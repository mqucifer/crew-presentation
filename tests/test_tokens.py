"""Token and contrast checks: validate the site's CSS against the design system's rules."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
import tools.token_check as token_check


def test_real_site_css_has_no_raw_colours():
    """The site's own CSS uses only design-system tokens: no raw colour literals."""
    site = (REPO_ROOT / "site" / "css" / "site.css").read_text()
    assert token_check.find_raw_colours(site) == []


def test_surface_text_pair_passes_both_themes(tmp_path):
    """AC1: background var(--color-surface) + child colour var(--color-text) -> the pair passes in both themes."""
    site = tmp_path / "site.css"
    site.write_text(
        ".panel { background: var(--color-surface); }\n"
        ".panel .label { color: var(--color-text); }\n"
    )
    result = token_check.run_check(site, _design_css())
    assert result.exit_code == 0, result.report
    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert (pair.fg, pair.bg) == ("--color-text", "--color-surface")
    assert pair.light_ratio >= 4.5
    assert pair.dark_ratio >= 4.5


def test_raw_hex_outside_token_block_fails(tmp_path):
    """AC2: a raw '#FF0000' outside a token block -> non-zero, naming the line and value as raw / not a token."""
    site = tmp_path / "site.css"
    site.write_text(".x { padding: 4px; }\n.y { color: #FF0000; }\n")
    result = token_check.run_check(site, _design_css())
    assert result.exit_code != 0
    assert "#FF0000" in result.report
    assert "raw" in result.report
    assert "not a token" in result.report
    assert "line 2" in result.report


def test_text_on_bg_meets_minimum_and_check_passes(tmp_path):
    """AC3: --color-text on --color-bg is >= 4.5 in both themes; the check exits 0."""
    assert token_check.contrast_ratio("#2E1F14", "#F6EFE3") >= 4.5  # light
    assert token_check.contrast_ratio("#F3E9DA", "#1C1510") >= 4.5  # dark
    site = tmp_path / "site.css"
    site.write_text(
        ".page { background: var(--color-bg); }\n"
        ".page h1 { color: var(--color-text); }\n"
    )
    result = token_check.run_check(site, _design_css())
    assert result.exit_code == 0, result.report
    assert result.pairs and result.pairs[0].fg == "--color-text"


def test_placeholder_site_css_passes(tmp_path):
    """AC4: a placeholder site.css (the marker, no rules) -> exit 0, no violations."""
    site = tmp_path / "site.css"
    site.write_text("crew:placeholder\n")
    result = token_check.run_check(site, _design_css())
    assert result.exit_code == 0, result.report
    assert result.violations == []


def test_surface_text_pair_named_in_output(tmp_path):
    """AC5: the report names the pair under test (--color-surface, --color-text) as passing both themes."""
    site = tmp_path / "site.css"
    site.write_text(
        ".panel { background: var(--color-surface); }\n"
        ".panel .label { color: var(--color-text); }\n"
    )
    result = token_check.run_check(site, _design_css())
    assert result.exit_code == 0, result.report
    assert "--color-surface" in result.report
    assert "--color-text" in result.report
    pair = result.pairs[0]
    assert pair.light_ratio >= 4.5 and pair.dark_ratio >= 4.5


def test_attempt_chart_raw_hex_fails(tmp_path):
    """AC6: '.attempt-chart { background: #333333; }' -> non-zero, naming the value and line."""
    site = tmp_path / "site.css"
    site.write_text(".attempt-chart { background: #333333; }\n")
    result = token_check.run_check(site, _design_css())
    assert result.exit_code != 0
    assert "#333333" in result.report
    assert ("raw" in result.report) or ("not a token" in result.report)
    assert "line 1" in result.report


def test_placeholder_comment_reports_no_rules(tmp_path):
    """AC7: a placeholder comment with no rules -> exit 0, a 'no rules' message, 0 violations, 0 pairs."""
    site = tmp_path / "site.css"
    site.write_text("/* crew:placeholder */\n")
    result = token_check.run_check(site, _design_css())
    assert result.exit_code == 0, result.report
    assert "no rules" in result.report.lower()
    assert result.violations == []
    assert result.pairs == []


def _design_css() -> Path:
    """Return the path to the design-system CSS fetched by setup into ./.package/."""
    from tools.setup import design_system_css, DESIGN_SYSTEM_VERSION_FILE
    version = DESIGN_SYSTEM_VERSION_FILE.read_text().strip()
    return design_system_css(version)
