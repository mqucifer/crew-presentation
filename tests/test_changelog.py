"""The changelog's rules: what waits for a release is towncrier fragments, and only a
release writes CHANGELOG.md (mqucifer/crew#1010).

Each change adds changes/<issue>.<kind>.md, <kind> a Keep a Changelog section, and a
release builds its dated section from them below towncrier's start line, deleting
them. A fragment misnamed is never collected, so it's caught here.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
CHANGES = REPO_ROOT / "changes"

KINDS = ["added", "changed", "deprecated", "removed", "fixed", "security"]
FRAGMENT = re.compile(rf"^(\+[^./]+|\d+)\.({'|'.join(KINDS)})(\.\d+)?\.md$")
NOT_FRAGMENTS = {"README.md", ".gitkeep"}
START = "<!-- towncrier release notes start -->"
RELEASED = re.compile(r"^## \[(\d+\.\d+\.\d+[^\]]*)\]", re.MULTILINE)


def changelog_problems(text: str, names: list[str]) -> list[str]:
    """Each file in changes/ that isn't a fragment, and a start line missing or below a
    released section."""
    problems = [
        f"changes/{name} is not a fragment: name it <issue>.<kind>.md, <kind> one of "
        f"{', '.join(KINDS)}"
        for name in names
        if name not in NOT_FRAGMENTS and not FRAGMENT.match(name)
    ]
    start = text.find(START)
    if start == -1:
        return problems + [f"CHANGELOG.md has no towncrier start line {START!r}"]
    first = RELEASED.search(text)
    if first and first.start() < start:
        problems.append(f"{first.group(0)!r} is above the towncrier start line {START!r}")
    return problems


def test_the_changelog_and_fragments_keep_the_rules():
    names = sorted(p.name for p in CHANGES.iterdir())
    assert changelog_problems(CHANGELOG.read_text(), names) == []
    assert "README.md" in names


def test_each_kind_with_an_issue_or_none_is_a_fragment():
    names = [f"305.{kind}.md" for kind in KINDS] + ["+docs.fixed.md", "305.fixed.2.md"]
    assert changelog_problems(CHANGELOG.read_text(), names) == []


def test_a_misnamed_fragment_is_named():
    (problem,) = changelog_problems(CHANGELOG.read_text(), ["305.improved.md"])
    assert "changes/305.improved.md" in problem


def test_the_start_line_is_above_every_released_section():
    text = CHANGELOG.read_text()
    (problem,) = changelog_problems(text.replace(START, "", 1), [])
    assert START in problem
    newest = RELEASED.search(text).group(0)
    moved = text.replace(START, "", 1).replace(newest, f"{newest}\n\n{START}", 1)
    (problem,) = changelog_problems(moved, [])
    assert newest in problem


def test_entries_left_under_unreleased_from_before_the_fragments_break_no_rule():
    """A fix merged the old way waits for the next release, which collects it."""
    text = CHANGELOG.read_text().replace(
        START, f"{START}\n\n## [Unreleased]\n\n### Fixed\n\n- An old-way fix\n", 1
    )
    assert changelog_problems(text, []) == []


def test_no_test_reads_a_specific_fragment_file():
    """No test constructs a path to a specific fragment under changes/; a release
    deletes fragments, so such a test would break after the next release."""
    fragment_ref = re.compile(r'(?:"changes"|CHANGES)\s*/\s*"(\S+\.md)"')
    for py_file in sorted((REPO_ROOT / "tests").rglob("*.py")):
        text = py_file.read_text()
        for match in fragment_ref.finditer(text):
            name = match.group(1)
            if name == "README.md":
                continue
            assert False, (
                f"{py_file.name} references a specific fragment under the "
                f"changes directory; a release deletes fragments, so this "
                f"test would break"
            )


