"""Site contrast and token checks against the design system's rules.

Two checks, both run against the site's own CSS (site/css/site.css) using the
design system's token values (fetched into ./.package/ by setup):

- **Token check** (find_raw_colours): every colour in the site's CSS must come
  from a design-system token. A raw hex, rgb() or hsl() value outside a
  :root / [data-theme] token block is a violation, named by line and value.
- **Contrast check** (contrast_ratio + text_background_pairs): every
  text-on-background pair the site's CSS uses must meet WCAG 4.5:1 in both the
  light and dark themes, using the token values the design system defines.

run_check runs both and returns a CheckResult; its exit_code is 0 when there
are no raw-colour violations and no pair falls below the minimum contrast.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# WCAG 2.1 minimum contrast ratio for normal text.
MIN_CONTRAST = 4.5

# A CSS colour literal: #RGB / #RGBA / #RRGGBB / #RRGGBBAA, or rgb(a)() / hsl(a)().
_COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}|(?:rgba?|hsla?)\(\s*\d")


@dataclass
class RawColour:
    line: int
    value: str


@dataclass
class Pair:
    fg: str
    bg: str
    light_ratio: float
    dark_ratio: float

    @property
    def ok(self) -> bool:
        return self.light_ratio >= MIN_CONTRAST and self.dark_ratio >= MIN_CONTRAST


@dataclass
class CheckResult:
    violations: list
    pairs: list
    rules_found: bool
    report: str

    @property
    def ok(self) -> bool:
        return not self.violations and all(p.ok for p in self.pairs)

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def _parse_hex(value: str):
    """'#RRGGBB' (or '#RGB', with optional alpha) -> (r, g, b), or None."""
    value = value.lstrip("#")
    if len(value) in (4, 8):
        value = value[:3] if len(value) == 4 else value[:6]
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        return None
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _relative_luminance(rgb) -> float:
    """WCAG 2.1 relative luminance of an (r, g, b) tuple in 0..255."""

    def channel(c: int) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 contrast ratio between two hex colours, e.g. '#2E1F14'."""
    fg_rgb = _parse_hex(fg)
    bg_rgb = _parse_hex(bg)
    if fg_rgb is None or bg_rgb is None:
        raise ValueError(f"not a hex colour: {fg!r} or {bg!r}")
    l1 = _relative_luminance(fg_rgb)
    l2 = _relative_luminance(bg_rgb)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _blocks(css_text: str) -> list:
    """(selector, body, start, end) for each top-level `selector { body }` block."""
    blocks = []
    i, n = 0, len(css_text)
    while i < n:
        brace = css_text.find("{", i)
        if brace == -1:
            break
        selector = css_text[i:brace].strip()
        depth, j = 1, brace + 1
        while j < n and depth:
            if css_text[j] == "{":
                depth += 1
            elif css_text[j] == "}":
                depth -= 1
            j += 1
        blocks.append((selector, css_text[brace + 1 : j - 1], i, j))
        i = j
    return blocks


def parse_tokens(css_text: str) -> dict:
    """Map token name -> value for the light (:root) and dark ([data-theme]) blocks.

    Returns {"light": {token: value}, "dark": {token: value}}.
    """
    light: dict = {}
    dark: dict = {}
    for selector, body, _s, _e in _blocks(css_text):
        if re.search(r":root\b", selector):
            target = light
        elif "data-theme" in selector and "dark" in selector:
            target = dark
        else:
            continue
        for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;{}]+)", body):
            target[m.group(1).strip()] = m.group(2).strip()
    return {"light": light, "dark": dark}


def _token_block_lines(css_text: str) -> list:
    """1-based line spans of the :root / [data-theme] token-definition blocks."""
    spans = []
    for selector, _body, start, end in _blocks(css_text):
        if re.search(r":root\b", selector) or "data-theme" in selector:
            spans.append(
                (
                    css_text.count("\n", 0, start) + 1,
                    css_text.count("\n", 0, end) + 1,
                )
            )
    return spans


def find_raw_colours(css_text: str) -> list:
    """Raw colour literals in the site's CSS that do not come from a token.

    A colour literal (hex/rgb/hsl) is a violation unless it sits inside a
    :root / [data-theme] token block, where it is a token definition. Each
    violation names its line number and value.
    """
    spans = _token_block_lines(css_text)
    violations = []
    for lineno, line in enumerate(css_text.splitlines(), start=1):
        if any(a <= lineno <= b for a, b in spans):
            continue
        match = _COLOUR_LITERAL.search(line)
        if match:
            violations.append(RawColour(line=lineno, value=match.group(0)))
    return violations


def text_background_pairs(css_text: str) -> list:
    """The (foreground, background) token pairs the site's CSS uses.

    A foreground token is referenced in a `color:` declaration; a background
    token in a `background`/`background-color` declaration (a solid var() or a
    gradient stop). The site uses the cross-product of the two.
    """
    foreground = set()
    background = set()
    for line in css_text.splitlines():
        for m in re.finditer(r"\bcolor\s*:\s*var\((--[a-z0-9-]+)\)", line):
            foreground.add(m.group(1))
        for m in re.finditer(r"\bbackground(?:-color)?\s*:\s*([^;}]+)", line):
            for t in re.finditer(r"var\((--[a-z0-9-]+)\)", m.group(1)):
                background.add(t.group(1))
    return [(f, b) for f in sorted(foreground) for b in sorted(background)]


def _build_report(violations, pairs, rules_found) -> str:
    if not rules_found:
        return "No rules were found to check: 0 violations, 0 pairs tested."
    lines = []
    for v in violations:
        lines.append(f"line {v.line}: {v.value} is a raw colour (not a token)")
    for p in pairs:
        status = "pass" if p.ok else "FAIL"
        lines.append(
            f"pair: {p.fg} on {p.bg} -> light {p.light_ratio:.2f}:1, "
            f"dark {p.dark_ratio:.2f}:1 ({status})"
        )
    if not lines:
        lines.append("All checks passed: no raw colours, all pairs meet 4.5:1.")
    return "\n".join(lines) + f"\n{len(violations)} violations, {len(pairs)} pairs tested."


def run_check(site_css, design_css) -> CheckResult:
    """Run both the token check and the contrast check against the design system."""
    site_text = Path(site_css).read_text()
    design_text = Path(design_css).read_text()

    violations = find_raw_colours(site_text)
    tokens = parse_tokens(design_text)
    light, dark = tokens["light"], tokens["dark"]

    pairs = []
    for fg, bg in text_background_pairs(site_text):
        lf, ld = light.get(fg), dark.get(fg)
        lb, db = light.get(bg), dark.get(bg)
        if None in (lf, ld, lb, db):
            # A token the design system does not define: off-token, fail loudly.
            pairs.append(Pair(fg=fg, bg=bg, light_ratio=0.0, dark_ratio=0.0))
        else:
            pairs.append(
                Pair(
                    fg=fg,
                    bg=bg,
                    light_ratio=contrast_ratio(lf, lb),
                    dark_ratio=contrast_ratio(ld, db),
                )
            )

    rules_found = bool(re.search(r"{", site_text))
    return CheckResult(
        violations=violations,
        pairs=pairs,
        rules_found=rules_found,
        report=_build_report(violations, pairs, rules_found),
    )
