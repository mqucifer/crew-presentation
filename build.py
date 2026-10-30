"""Build the site: validate the package and write the assembled site to build/."""

import json
import re
import shutil
import sys
from pathlib import Path

import jinja2
import jsonschema

REPO_ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = REPO_ROOT / ".package"
DELIVERY_HISTORY_TAG = REPO_ROOT / "delivery-history.tag"
BUILD_DIR = REPO_ROOT / "build"
TEMPLATES_DIR = REPO_ROOT / "site" / "templates"
CSS_DIR = REPO_ROOT / "site" / "css"
JS_DIR = REPO_ROOT / "site" / "js"

SUPPORTED_MAJOR_VERSIONS = (1, 2)

TEMPLATE_MAP = {
    "replay.html": "replay.html",
    "story_journey.html": "story-journey.html",
}


def _package_dir() -> Path:
    """Locate the package directory under ./.package/ named by delivery-history.tag."""
    tag = DELIVERY_HISTORY_TAG.read_text().strip()
    d = PACKAGE_DIR / tag
    if not d.is_dir():
        print(f"ERROR: package directory not found: {d}", file=sys.stderr)
        sys.exit(1)
    return d


def _load_json(path: Path) -> dict:
    """Load and parse a JSON file, exiting with an error if it is missing."""
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text())


def _validate_against_schema(data, schema, file_label: str) -> None:
    """Validate data against a JSON schema; exit with an error naming the file on failure."""
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        messages = "; ".join(
            f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors[:5]
        )
        print(
            f"ERROR: {file_label} does not conform to its schema: {messages}",
            file=sys.stderr,
        )
        sys.exit(1)


def _check_schema_version(manifest: dict) -> None:
    """Exit with an error if the manifest's schema_version major is not supported."""
    version = manifest["schema_version"]
    match = re.fullmatch(r"(\d+)\.(\d+)(\.(\d+))?", version)
    if not match:
        print(f"ERROR: unrecognized schema_version format: {version}", file=sys.stderr)
        sys.exit(1)
    major = int(match.group(1))
    if major not in SUPPORTED_MAJOR_VERSIONS:
        print(
            f"ERROR: schema major version {major} is one the site cannot display "
            f"(supported: {SUPPORTED_MAJOR_VERSIONS})",
            file=sys.stderr,
        )
        sys.exit(1)


def _validate_package(pkg: Path) -> None:
    """Validate every data file in the package against the schema it carries."""
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


def _render_pages(pkg: Path) -> dict:
    """Render each page: one per sprint, one per story card, plus the other views."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )

    def url_for(endpoint, **kwargs):
        if endpoint == "static":
            return kwargs.get("filename", "")
        return ""

    env.globals["url_for"] = url_for

    design_system_version = (
        REPO_ROOT / "site" / "css" / "design-system.version"
    ).read_text().strip()
    env.globals["design_system_version"] = design_system_version

    manifest = _load_json(pkg / "manifest.json")
    index = _load_json(pkg / "delivery-history.json")
    sprints = index.get("sprints", [])
    crew_repository = index.get("crew_repository", "")
    sprint_metrics_answers = index.get("sprint_metrics", {}).get("answers", {})
    cards = index.get("cards", [])
    analysis_stories = index.get("analysis", {}).get("stories", [])
    analysis_sprints = index.get("analysis", {}).get("sprints", [])
    analysis_by_sprint: dict[str, dict] = {a["sprint"]: a for a in analysis_sprints}

    cards_by_key: dict[tuple, dict] = {}
    for card in cards:
        key = (card.get("number"), card.get("repo"))
        cards_by_key[key] = card

    env.globals["crew_repository"] = crew_repository

    pages = {}

    sprint_template = env.get_template("sprint_overview.html")
    for sprint in sprints:
        slug = _slug(sprint["name"])
        key = sprint["name"]
        if key not in sprint_metrics_answers:
            print(
                f"NOTE: sprint_metrics.answers has no key for sprint {key!r}; "
                f"skipping {slug}",
                file=sys.stderr,
            )
            continue
        metrics = sprint_metrics_answers[key]

        denominator = metrics.get("first_attempt_denominator") or 0
        numerator = metrics.get("first_attempt_numerator") or 0

        stories = []
        for story in analysis_stories:
            delivered = story.get("delivered")
            if not delivered:
                continue
            if isinstance(delivered, str):
                delivered_date = delivered[:10]
                if not (sprint["start"] <= delivered_date <= sprint["end"]):
                    continue

            card_key = (story["card"]["number"], story["card"]["repo"])
            card = cards_by_key.get(card_key)
            raw_blocks = story.get("blocks", [])
            if isinstance(raw_blocks, int):
                blocks = ["refused"] * (raw_blocks - 1) + ["landed"]
            elif raw_blocks:
                blocks = list(raw_blocks)
            else:
                blocks = []
            pattern = story.get("pattern", "")
            if pattern:
                status = pattern.replace("_", " ")
            else:
                status = "merged"
            stories.append(
                {
                    "number": story["card"]["number"],
                    "repo": story["card"]["repo"],
                    "title": card.get("title", "") if card else "",
                    "blocks": blocks,
                    "crew_fixes": story.get("crew_fixes", []),
                    "delivered": bool(delivered),
                    "pattern": pattern,
                    "status": status,
                }
            )

        changed = [
            {
                "text": e["text"],
                "label": _changed_label(e["measure"]),
                "previous": _format_changed_value(e["measure"], e["previous"]),
                "now": _format_changed_value(e["measure"], e["now"]),
            }
            for e in analysis_by_sprint.get(sprint["name"], {}).get("changed", [])
        ]
        decided = analysis_by_sprint.get(sprint["name"], {}).get("decided", [])

        context = {
            "sprints": sprints,
            "sprint": sprint,
            "metrics": metrics,
            "stats": {
                "throughput": _stat_value(metrics.get("throughput")),
                "first_try": _first_try_stat(
                    metrics.get("first_attempt_numerator"),
                    metrics.get("first_attempt_denominator"),
                ),
                "escalation_count": _stat_value(metrics.get("escalation_count")),
                "points_delivered": _stat_value(metrics.get("points_delivered")),
            },
            "cycle_time": _format_minutes(metrics.get("cycle_time_minutes")),
            "sprint_slug": slug,
            "stories": stories,
            "changed": changed,
            "decided": decided,
            "failure_causes": _build_failure_causes(metrics),
            "current_view": "sprint",
        }
        pages[slug] = sprint_template.render(**context)

    current_view_map = {
        "replay.html": "replay",
        "story_journey.html": "journey",
    }
    for template_name, output_name in TEMPLATE_MAP.items():
        template = env.get_template(template_name)
        context = {
            "manifest": manifest,
            "package": index,
            "sprint_slug": "",
            "current_view": current_view_map.get(template_name, "sprint"),
        }
        if template_name == "replay.html":
            current_sprint = sprints[-1] if sprints else {}
            context["current_sprint"] = current_sprint
            sprint_name = current_sprint.get("name", "")
            board_columns, board_cards = _build_board_state(
                pkg, index, sprint_name
            )
            context["board_columns"] = board_columns
            context["board_cards"] = board_cards
            events = _load_sprint_events(pkg, sprint_name, index)
            replay_cards = _build_replay_cards(events, cards)
            replay_data = {
                "sprint": sprint_name,
                "events": events,
                "cards": replay_cards,
            }
            context["replay_data_json"] = json.dumps(replay_data)
        pages[output_name] = template.render(**context)

    story_journey_template = env.get_template("story_journey.html")
    for card in cards:
        repo = card.get("repo", "")
        number = card.get("number")
        if not repo or number is None:
            continue
        slug = f"{repo.replace('/', '-')}-{number}.html"
        pages[f"stories/{slug}"] = story_journey_template.render(
            card=card,
            manifest=manifest,
            package=index,
            sprint_slug="",
            current_view="journey",
            static_prefix="../",
        )

    return pages


def _copy_assets() -> None:
    """Copy site/css/ and site/js/ into build/."""
    build_css = BUILD_DIR / "css"
    build_js = BUILD_DIR / "js"
    build_css.mkdir(parents=True, exist_ok=True)
    build_js.mkdir(parents=True, exist_ok=True)

    for f in sorted(CSS_DIR.iterdir()):
        if f.is_file():
            shutil.copy2(f, build_css / f.name)
    for f in sorted(JS_DIR.iterdir()):
        if f.is_file():
            shutil.copy2(f, build_js / f.name)


def main() -> None:
    pkg = _package_dir()
    _validate_package(pkg)
    pages = _render_pages(pkg)

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)

    for name, content in pages.items():
        path = BUILD_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    _copy_assets()
    print(f"Build complete: {BUILD_DIR}")


def _slug(name: str) -> str:
    """A sprint name as a filename: lowercase, spaces to hyphens, .html extension."""
    return name.lower().replace(" ", "-") + ".html"


def _normalize_failure_causes(raw) -> list[dict]:
    """Normalize sprint-metrics' top_failure_causes into [{'reason', 'count'}].

    The site's contract is a list of {reason, count} objects, but the answer
    shape has drifted across releases: a list of [reason, count] pairs, a
    {reason: count} mapping, or a bare list of reasons all carry the same
    information. Anything we cannot read yields a 0 count instead of a crash —
    the site shows what its package says, it does not compute the metric itself.
    """
    if not raw:
        return []
    if isinstance(raw, dict):
        return [
            {"reason": str(reason), "count": _as_count(count)}
            for reason, count in raw.items()
        ]
    if not isinstance(raw, (list, tuple)):
        return []
    causes = []
    for item in raw:
        if isinstance(item, dict):
            reason = item.get("reason", item.get("cause", ""))
            count = item.get("count", 0)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            reason, count = item[0], item[1]
        else:
            reason, count = item, 0
        causes.append({"reason": str(reason), "count": _as_count(count)})
    return causes


def _as_count(value) -> int:
    """Coerce a count value to a non-negative int; anything else is 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, float):
        return int(value) if value > 0 else 0
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _build_failure_causes(metrics: dict) -> list[dict]:
    """Sprint-metrics' top_failure_causes as ready-to-render bar-chart rows.

    Each row carries the reason (mapped from code to display string via
    CAUSE_LABELS), its count, the bar's width as a percentage of the largest
    count, and whether the reason is the unrecorded placeholder. Widths are
    computed here (display sizing, not a metric) so the template only prints
    values and the build never divides by zero.
    """
    causes = _normalize_failure_causes(metrics.get("top_failure_causes"))
    max_count = max((c["count"] for c in causes), default=0)
    return [
        {
            "reason": CAUSE_LABELS.get(c["reason"], "Cause not recorded"),
            "count": c["count"],
            "width": int(round(c["count"] / max_count * 100)) if max_count else 0,
            "unrecorded": c["reason"] not in CAUSE_LABELS
            or c["reason"] == "unrecorded",
        }
        for c in causes
    ]


def _stat_value(value) -> str:
    """A stat's numeric value as display text: the number, or an em dash when missing.

    A missing value (JSON null) renders '—' rather than the programming literal
    'None', keeping the page readable for a public visitor.
    """
    if value is None:
        return "—"
    return str(value)


def _first_try_stat(numerator, denominator) -> str:
    """The first-try stat: 'X of Y' when present, an em dash when missing."""
    if numerator is None or denominator is None:
        return "—"
    return f"{numerator} of {denominator}"


def _format_minutes(total_minutes) -> str:
    """A metric's minutes as hours and minutes: '1 hr 29 min', '1 hr', '0 min'.

    Zero units are omitted and days are never shown (R2), so a sprint that
    ran for a few hundred minutes reads in the reader's terms, not as
    '0 days'. A missing value (a fixture without cycle_time_minutes) renders
    empty rather than inventing one.
    """
    if total_minutes is None:
        return ""
    hours, minutes = divmod(int(total_minutes), 60)
    if hours == 0:
        return f"{minutes} min"
    if minutes == 0:
        return f"{hours} hr"
    return f"{hours} hr {minutes} min"


def _format_changed_value(measure: str, value) -> str:
    """Format a changed-trend value for display.

    Time measures (cycle_time, lead_time) are shown as hours and minutes;
    other measures are shown as their raw number.
    """
    if value is None:
        return ""
    if measure in ("cycle_time_days", "lead_time_days"):
        total_minutes = round(value * 24 * 60)
        return _format_minutes(total_minutes)
    if measure in ("cycle_time_minutes", "lead_time_minutes"):
        return _format_minutes(round(value))
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _changed_label(measure: str) -> str:
    """A human-readable label for a changed-trend measure.

    Time measures show as 'cycle time' or 'lead time'; non-time measures
    show as their human-readable name.
    """
    LABELS = {
        "cycle_time_days": "cycle time",
        "cycle_time_minutes": "cycle time",
        "lead_time_minutes": "lead time",
        "lead_time_days": "lead time",
        "first_attempt_rate_percent": "first-attempt rate",
        "escalation_count": "escalations",
        "points_delivered": "points delivered",
        "throughput": "stories delivered",
        "blocked_aging_days": "days blocked",
        "superseded_count": "stories superseded",
        "crew_fixes_merged": "crew fixes merged",
        "wip_violations": "WIP violations",
    }
    return LABELS.get(measure, measure)


CAUSE_LABELS = {
    "test_assertion_failed": "A test's assertion failed",
    "already_exists": '"already exists"',
    "must_create_or_edit_file": "Must create or edit a file",
    "undefined_name": "Undefined name (lint)",
    "no_test_written": "No test written",
    "unrecorded": "Cause not recorded",
}


_COLUMN_ORDER: list[str] = [
    "Inbox (Goals)",
    "Needs Refinement",
    "Ready",
    "Sprint Backlog",
    "In Progress",
    "Reviewing",
    "QAing",
    "Merging",
    "Done",
    "Blocked",
]


def _board_column_order(columns: set[str]) -> list[str]:
    """Order column names by the design system's tone-table order."""
    return [c for c in _COLUMN_ORDER if c in columns]


def _load_sprint_events(pkg: Path, sprint_name: str, index: dict) -> list[dict]:
    """Load events for a sprint from the package's events file."""
    periods = index.get("periods", [])
    for period in periods:
        if period.get("sprint") == sprint_name:
            events_file = pkg / period["file"]
            if events_file.is_file():
                data = _load_json(events_file)
                return data.get("events", [])
    return []


def _build_board_state(
    pkg: Path,
    index: dict,
    sprint_name: str,
) -> tuple[list[str], dict[str, list[dict]]]:
    """Compute the board's columns and place each card in its initial column.

    Returns (columns, board_cards) where columns is an ordered list of column
    names and board_cards maps each column name to a list of card dicts with
    'link_text' and 'title' keys.
    """
    events = _load_sprint_events(pkg, sprint_name, index)
    cards = index.get("cards", [])

    if not events:
        return [], {}

    # Determine columns from events
    columns: set[str] = set()
    for event in events:
        if event.get("from_column"):
            columns.add(event["from_column"])
        if event.get("to_column"):
            columns.add(event["to_column"])
    ordered_columns = _board_column_order(columns)

    # Index cards by (number, repo)
    cards_by_key: dict[tuple, dict] = {}
    for card in cards:
        key = (card.get("number"), card.get("repo"))
        cards_by_key[key] = card

    # Find each card's earliest event
    earliest: dict[tuple, dict] = {}
    for event in events:
        card_ref = event.get("card")
        if not card_ref:
            continue
        key = (card_ref.get("number"), card_ref.get("repo"))
        at = event.get("at", "")
        if key not in earliest or at < earliest[key].get("at", ""):
            earliest[key] = event

    # Place cards in their initial column
    board: dict[str, list[dict]] = {col: [] for col in ordered_columns}
    for key, event in earliest.items():
        col = event.get("from_column", "")
        if col not in board:
            continue
        card = cards_by_key.get(key)
        if card is None:
            continue
        url = card.get("url", "")
        match = re.match(
            r"https://github\.com/([^/]+)/([^/]+)/issues/\d+", url
        )
        if match:
            display_repo = f"{match.group(1)}/{match.group(2)}"
        else:
            display_repo = card.get("repo", "")
        number = card.get("number", "")
        board[col].append({
            "link_text": f"[{display_repo}#{number}]({url})",
            "title": card.get("title", ""),
        })

    return ordered_columns, board


def _build_replay_cards(events: list[dict], cards: list[dict]) -> list[dict]:
    """Build the cards array for the replay JSON.

    One entry per unique card referenced by events, with title from the
    package's cards array or empty string when not found.
    """
    cards_by_key: dict[tuple, dict] = {}
    for card in cards:
        key = (card.get("number"), card.get("repo"))
        cards_by_key[key] = card

    seen: set[tuple] = set()
    result: list[dict] = []
    for event in events:
        card_ref = event.get("card")
        if not card_ref:
            continue
        key = (card_ref.get("number"), card_ref.get("repo"))
        if key in seen:
            continue
        seen.add(key)
        card = cards_by_key.get(key)
        result.append({
            "number": card_ref.get("number"),
            "repo": card_ref.get("repo", ""),
            "title": card.get("title", "") if card else "",
        })
    return result


if __name__ == "__main__":
    main()
