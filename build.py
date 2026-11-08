"""Build the site: validate the package and write the assembled site to build/."""

import json
import re
import shutil
import sys
from datetime import datetime, timedelta
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

SUPPORTED_MAJOR_VERSIONS = (1, 2, 3, 4)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Event kinds that are per-tool or per-turn internals, omitted from the
# journey timeline so it stays a readable life cycle, not a machine log.
_OMITTED_EVENT_KINDS = frozenset(
    {"model_call", "tool_call", "session_turn", "session_compacted"}
)

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
    timezone_label = _timezone_label(index["timezone"]) if index.get("timezone") else None

    cards_by_key: dict[tuple, dict] = {}
    for card in cards:
        key = (card.get("number"), card.get("repo"))
        cards_by_key[key] = card

    env.globals["crew_repository"] = crew_repository
    env.globals["static_prefix"] = ""

    pages = {}

    sprint_template = env.get_template("sprint_overview.html")
    default_sprint_slug = ""
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
        epic_groups = []
        has_analysis = bool(analysis_stories)
        if has_analysis:
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
        else:
            sprint_events = _load_sprint_events(pkg, sprint["name"], index)
            epic_groups = _epic_groups(
                cards, sprint["name"], metrics.get("roster"), sprint_events
            )

        analysis_changed = analysis_by_sprint.get(sprint["name"], {}).get(
            "changed", []
        )
        if analysis_changed:
            changed = [
                {
                    "text": e["text"],
                    "label": _changed_label(e["measure"]),
                    "previous": _format_changed_value(e["measure"], e["previous"]),
                    "now": _format_changed_value(e["measure"], e["now"]),
                }
                for e in analysis_changed
                if e["measure"] != "escalation_count"
            ]
        else:
            prior = metrics.get("prior")
            if prior:
                changed = _changed_from_metrics(metrics, prior)
            else:
                changed = []
        decided = analysis_by_sprint.get(sprint["name"], {}).get("decided", [])
        if not decided:
            sprint_events = _load_sprint_events(pkg, sprint["name"], index)
            decided = _decided_from_events_and_cards(sprint_events, cards, sprint)

        roster = metrics.get("roster")
        released_epics = []
        achieved_goals = []
        if roster:
            for ref in (roster.get("released_epics") or []):
                repo, num_str = ref.rsplit("#", 1)
                card = cards_by_key.get((int(num_str), repo))
                if card:
                    released_epics.append(card)
            for ref in (roster.get("achieved_goals") or []):
                repo, num_str = ref.rsplit("#", 1)
                card = cards_by_key.get((int(num_str), repo))
                if card:
                    achieved_goals.append(card)

        sent_back_events = _load_sprint_events(pkg, sprint["name"], index)
        sent_back_rows = _build_sent_back_rows(sent_back_events)
        left_open_rows = _left_open_rows(sent_back_events, cards, sprint)

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
                "points_delivered": _stat_value(metrics.get("points_delivered")),
            },
            "cycle_time": _format_minutes(metrics.get("cycle_time_minutes")),
            "sprint_slug": slug,
            "stories": stories,
            "epic_groups": epic_groups,
            "has_analysis": has_analysis,
            "changed": changed,
            "decided": decided,
            "failure_causes": _build_failure_causes(metrics),
            "sent_back_rows": sent_back_rows,
            "left_open_rows": left_open_rows,
            "roster_released_epics": released_epics,
            "roster_achieved_goals": achieved_goals,
            "model_time_split": _build_model_time_split(metrics),
            "idle_time": _build_idle_time(metrics),
            "current_view": "sprint",
            "timezone_label": timezone_label,
        }
        pages[slug] = sprint_template.render(**context)
        default_sprint_slug = slug

    current_view_map = {
        "replay.html": "replay",
        "story_journey.html": "journey",
    }
    for template_name, output_name in TEMPLATE_MAP.items():
        template = env.get_template(template_name)
        context = {
            "manifest": manifest,
            "package": index,
            "sprint_slug": default_sprint_slug,
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
    all_events = _load_all_events(pkg, index)
    for card in cards:
        repo = card.get("repo", "")
        number = card.get("number")
        if not repo or number is None:
            continue
        slug = f"{repo.replace('/', '-')}-{number}.html"
        # Find the analysis story for this card
        story_entry = None
        for s in analysis_stories:
            if s.get("card", {}).get("number") == number and s.get("card", {}).get("repo") == repo:
                story_entry = s
                break
        # Load and format events for this card, omitting internal per-tool
        # and per-turn events that would make the timeline unreadable.
        card_events = _filter_events_by_card(all_events, number, repo)
        event_dates = {e.get("at", "")[:10] for e in card_events if e.get("at")}
        include_date = len(event_dates) > 1
        formatted_events = []
        for e in card_events:
            text = _format_event_description(e)
            if text is None:
                continue
            formatted_events.append(
                {
                    "time": _format_event_time(e.get("at", ""), include_date),
                    "text": text,
                }
            )
        # Cost data
        wall_clock = None
        model_calls = None
        if story_entry:
            wcs = story_entry.get("wall_clock_seconds")
            if wcs is not None:
                wall_clock = _format_minutes(round(wcs / 60))
            cost = story_entry.get("cost")
            if cost:
                model_calls = cost.get("model_calls")
        pages[f"stories/{slug}"] = story_journey_template.render(
            card=card,
            manifest=manifest,
            package=index,
            sprint_slug=default_sprint_slug,
            current_view="journey",
            static_prefix="../",
            events=formatted_events,
            wall_clock=wall_clock,
            model_calls=model_calls,
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


def _timezone_label(tz: str) -> str:
    """A human-readable zone name from an IANA timezone identifier.

    'America/Chicago' becomes 'Chicago'; 'UTC' stays 'UTC'.
    """
    if "/" in tz:
        return tz.rsplit("/", 1)[-1]
    return tz


def _status_tone(status) -> str:
    """A board status's badge tone, in the design system's own words.

    The board's columns map onto the design system's badge tones: Done is
    done, the working columns are active, the blocked columns are blocked,
    and everything that is waiting on someone is waiting. An empty status
    reads as waiting.
    """
    if not status:
        return "waiting"
    s = str(status).strip()
    if s == "Done":
        return "done"
    if s in ("In Progress", "Reviewing", "QAing", "Merging", "Sprint Backlog"):
        return "active"
    if s in ("Blocked", "Refused"):
        return "blocked"
    return "waiting"


def _status_label(card: dict) -> str:
    """The badge's label: the board's own words, with a superseded story
    reading 'Closed, not planned' regardless of its Done status."""
    if card.get("closed_as") == "not_planned":
        return "Closed, not planned"
    return card.get("status") or ""


def _story_attempt_blocks(
    events: list[dict] | None, repo, number
) -> tuple[list[str], list[int], bool]:
    """The story's attempt blocks, read from the sprint's events.

    Returns (blocks, crew_fix_numbers, escalated) where blocks is a list of
    block-type strings in the order the events record them:
    'missed' for each attempt that did not land, 'blocked' for each time the
    story was blocked, 'crew-fix' for each merged fix to the crew the story
    references, and 'landed' for the attempt that landed.
    """
    if not events or repo is None or number is None:
        return [], [], False

    blocks: list[str] = []
    crew_fix_numbers: list[int] = []
    escalated = False
    seen_sent_back_rounds: set = set()

    for event in events:
        kind = event.get("kind")

        if kind == "attempt":
            card = event.get("card")
            if card and card.get("repo") == repo and card.get("number") == number:
                blocks.append("missed")

        elif kind == "sent_back":
            card = event.get("card")
            if card and card.get("repo") == repo and card.get("number") == number:
                round_val = event.get("round")
                if round_val is None:
                    blocks.append("missed")
                else:
                    if round_val not in seen_sent_back_rounds:
                        seen_sent_back_rounds.add(round_val)
                        blocks.append("missed")

        elif kind == "card_moved":
            card = event.get("card")
            if (
                card
                and card.get("repo") == repo
                and card.get("number") == number
                and event.get("to_column") == "Blocked"
            ):
                blocks.append("blocked")

        elif kind == "escalated":
            card = event.get("card")
            if card and card.get("repo") == repo and card.get("number") == number:
                escalated = True

        elif kind == "pull_merged":
            crews_own = event.get("crews_own", False)
            about = event.get("about") or []
            closes = event.get("closes") or []
            in_about = any(
                ref.get("repo") == repo and ref.get("number") == number
                for ref in about
            )
            in_closes = any(
                ref.get("repo") == repo and ref.get("number") == number
                for ref in closes
            )
            if crews_own and in_about:
                blocks.append("crew-fix")
                crew_fix_numbers.append(event.get("number", 0))
            elif not crews_own and in_closes:
                blocks.append("landed")

    return blocks, crew_fix_numbers, escalated


def _story_happened_line(
    blocks: list[str],
    card: dict,
    delivered: bool,
    crew_fix_numbers: list[int],
    escalated: bool,
) -> str:
    """One plain-words line saying what happened to the story."""
    if card.get("closed_as") == "not_planned":
        return "Superseded (closed as not planned) and never built."

    missed_count = blocks.count("missed")
    blocked_count = blocks.count("blocked")
    landed = "landed" in blocks

    if delivered:
        if missed_count == 0 and not blocked_count and not crew_fix_numbers:
            return "Landed first try."
        parts: list[str] = []
        if missed_count:
            parts.append(
                f"Missed {missed_count} time{'s' if missed_count != 1 else ''}"
            )
        if blocked_count:
            parts.append(
                f"was blocked{f' {blocked_count} times' if blocked_count > 1 else ''}"
            )
        if crew_fix_numbers:
            names = " and ".join(f"crew#{n}" for n in crew_fix_numbers)
            parts.append(f"{names} merged")
        if escalated:
            return (", ".join(parts) + ", then landed after it was escalated.")
        return (", ".join(parts) + ", then landed.") if parts else "Landed."

    # Not delivered
    status = card.get("status") or ""
    if status == "Blocked":
        parts = []
        if missed_count:
            parts.append(
                f"missed {missed_count} time{'s' if missed_count != 1 else ''}"
            )
        if blocked_count:
            parts.append(
                f"was blocked {blocked_count} time{'s' if blocked_count != 1 else ''} first"
            )
        if parts:
            return "Blocked now, " + " and ".join(parts) + "."
        return "Blocked now."
    if missed_count:
        return (
            f"Not delivered yet, missed {missed_count} time"
            f"{'s' if missed_count != 1 else ''} so far."
        )
    return "Not delivered yet."


def _epic_groups(
    cards: list[dict], sprint_name: str, roster, events: list[dict] | None = None
) -> list[dict]:
    """Group the sprint's cards under their epics.

    Every card whose sprint is this sprint's name becomes a row, whatever its
    status, type or closed state. The rows are grouped under their epic's
    heading, where the epic is the card's parent (by the card's parent number
    and its own repo). A story with no epic parent, or whose parent card is
    not an Epic, is grouped under a 'not part of an epic' heading and is never
    dropped.

    roster is the sprint answer's roster (a dict, or None when the answer
    carries no roster). roster.completed_stories marks which of the rows are
    delivered; it never decides which rows appear. A roster entry that names
    no card in the sprint adds no row and is counted nowhere.
    """
    cards_by_key: dict[tuple, dict] = {}
    for card in cards:
        key = (card.get("number"), card.get("repo"))
        cards_by_key[key] = card

    # The rows the roster names delivered: a set of (number, repo).
    has_roster = isinstance(roster, dict) and isinstance(
        roster.get("completed_stories"), (list, tuple)
    )
    delivered: set[tuple] = set()
    if has_roster:
        for ref in roster.get("completed_stories") or []:
            if not isinstance(ref, str) or "#" not in ref:
                continue
            repo, _, number_str = ref.partition("#")
            try:
                number = int(number_str)
            except ValueError:
                continue
            delivered.add((number, repo))

    # The sprint's cards, in package order.
    sprint_cards = [c for c in cards if c.get("sprint") == sprint_name]

    # Group each sprint card under its epic (or the no-epic group).
    groups: dict[tuple, list[dict]] = {}
    for card in sprint_cards:
        repo = card.get("repo")
        parent = card.get("parent")
        epic_card = cards_by_key.get((parent, repo)) if parent is not None else None
        if epic_card is not None and epic_card.get("type") == "Epic":
            key: tuple = ("epic", parent, repo)
        else:
            key = ("no-epic", None, None)
        groups.setdefault(key, []).append(card)

    # Order the groups: epics by their card's position in the package, then the
    # no-epic group last.
    epic_index: dict[tuple, int] = {}
    for i, card in enumerate(cards):
        if card.get("type") == "Epic":
            epic_index[(card.get("number"), card.get("repo"))] = i

    def order(key):
        if key[0] == "epic":
            return (
                0,
                epic_index.get((key[1], key[2]), 10**9),
                key[2] or "",
                key[1] or 0,
            )
        return (1, 0, "", 0)

    result: list[dict] = []
    for key in sorted(groups, key=order):
        rows: list[dict] = []
        done_count = 0
        for card in groups[key]:
            is_delivered = (card.get("number"), card.get("repo")) in delivered
            if is_delivered:
                done_count += 1
            blocks, crew_fix_numbers, escalated = _story_attempt_blocks(
                events, card.get("repo"), card.get("number")
            )
            status_label = _status_label(card)
            rows.append(
                {
                    "repo": card.get("repo") or "",
                    "number": card.get("number"),
                    "title": card.get("title") or "",
                    "status": status_label,
                    "status_tone": _status_tone(status_label),
                    "delivered": is_delivered,
                    "blocks": blocks,
                    "happened_line": _story_happened_line(
                        blocks,
                        card,
                        is_delivered,
                        crew_fix_numbers,
                        escalated,
                    ),
                }
            )
        group: dict = {
            "rows": rows,
            "done_count": done_count,
            "total_count": len(rows),
            "has_roster": has_roster,
            "is_epic": False,
            "epic_repo": None,
            "epic_number": None,
            "epic_title": None,
            "epic_status": None,
            "epic_status_tone": None,
            "has_goal": False,
            "goal_repo": None,
            "goal_number": None,
            "goal_title": None,
        }
        if key[0] == "epic":
            _, parent, repo = key
            epic_card = cards_by_key.get((parent, repo), {})
            goal_parent = epic_card.get("parent")
            goal_card = (
                cards_by_key.get((goal_parent, repo))
                if goal_parent is not None
                else None
            )
            has_goal = goal_card is not None and goal_card.get("type") == "Goal"
            group.update(
                {
                    "is_epic": True,
                    "epic_repo": repo,
                    "epic_number": parent,
                    "epic_title": epic_card.get("title") or "",
                    "epic_status": epic_card.get("status") or "",
                    "epic_status_tone": _status_tone(epic_card.get("status")),
                    "has_goal": has_goal,
                    "goal_repo": goal_card.get("repo") if has_goal else None,
                    "goal_number": goal_card.get("number") if has_goal else None,
                    "goal_title": goal_card.get("title") if has_goal else None,
                }
            )
        result.append(group)
    return result


def _normalize_failure_causes(raw) -> list[dict]:
    """Normalize sprint-metrics' top_failure_causes into [{'reason', 'count', 'recorded'}].

    The site's contract is a list of {reason, count} objects, but the answer
    shape has drifted across releases: 2.0.0 carries a list of {class, role,
    count} entries; 1.x carries a map of cause-code to count; and earlier
    shapes carry a list of [reason, count] pairs, a list of {reason, count}
    objects, or a bare list of reasons. Each carries the same information.

    A 2.0.0 entry's class is a recorded cause and is shown as-is, so it is
    flagged recorded=True and its reason is the class value; every other shape
    (a 1.x map key, a reason/cause field, or a bare code) is looked up in
    CAUSE_LABELS by the caller and flagged recorded=False. Anything we cannot
    read yields a 0 count instead of a crash — the site shows what its package
    says, it does not compute the metric itself.
    """
    if not raw:
        return []
    if isinstance(raw, dict):
        return [
            {"reason": str(reason), "count": _as_count(count), "recorded": False}
            for reason, count in raw.items()
        ]
    if not isinstance(raw, (list, tuple)):
        return []
    causes = []
    for item in raw:
        if isinstance(item, dict):
            class_code = item.get("class")
            if class_code is not None:
                # 2.0.0: {class, role, count} — the class is the recorded cause
                reason = str(class_code)
                count = item.get("count", 0)
                recorded = bool(reason)
            else:
                reason = item.get("reason", item.get("cause", ""))
                count = item.get("count", 0)
                recorded = False
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            reason, count = item[0], item[1]
            recorded = False
        else:
            reason, count = item, 0
            recorded = False
        causes.append(
            {"reason": str(reason), "count": _as_count(count), "recorded": recorded}
        )
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

    Each row carries the reason (a 2.0.0 class shown as-is, or a 1.x reason
    code mapped to a display string via CAUSE_LABELS), its count, the bar's
    width as a percentage of the largest count, and whether the reason is the
    unrecorded placeholder. Widths are computed here (display sizing, not a
    metric) so the template only prints values and the build never divides by
    zero.
    """
    causes = _normalize_failure_causes(metrics.get("top_failure_causes"))
    max_count = max((c["count"] for c in causes), default=0)
    rows = []
    for c in causes:
        if c["recorded"]:
            reason = c["reason"]
            unrecorded = False
        else:
            reason = CAUSE_LABELS.get(c["reason"], "Cause not recorded")
            unrecorded = c["reason"] not in CAUSE_LABELS or c["reason"] == "unrecorded"
        rows.append(
            {
                "reason": reason,
                "count": c["count"],
                "width": int(round(c["count"] / max_count * 100)) if max_count else 0,
                "unrecorded": unrecorded,
            }
        )
    return rows


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
    '0 days'. A missing value (JSON null) renders '—', the same mark
    _stat_value uses for other missing stats.
    """
    if total_minutes is None:
        return "—"
    hours, minutes = divmod(int(total_minutes), 60)
    if hours == 0:
        return f"{minutes} min"
    if minutes == 0:
        return f"{hours} hr"
    return f"{hours} hr {minutes} min"


def _format_changed_value(measure: str, value) -> str:
    """Format a changed-trend value for display.

    Time measures (cycle_time, lead_time) are shown as hours and minutes;
    first_attempt_rate_percent is shown with a '%' unit;
    other measures are shown as their raw number.
    """
    if value is None:
        return ""
    if measure in ("cycle_time_days", "lead_time_days"):
        total_minutes = round(value * 24 * 60)
        return _format_minutes(total_minutes)
    if measure in ("cycle_time_minutes", "lead_time_minutes"):
        return _format_minutes(round(value))
    if measure == "first_attempt_rate_percent":
        if isinstance(value, float) and value == int(value):
            return f"{int(value)}%"
        return f"{value}%"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _format_metrics_value(measure: str, value) -> str:
    """Format a value for the metrics-derived 'What changed' fallback.

    Time measures always show both hours and minutes (e.g. '0 hr 26 min');
    first_attempt_rate_percent is shown with a '%' unit;
    other measures are shown as their raw number.
    """
    if value is None:
        return ""
    if measure in ("cycle_time_minutes", "lead_time_minutes"):
        total_minutes = round(value)
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours} hr {minutes} min"
    if measure in ("cycle_time_days", "lead_time_days"):
        total_minutes = round(value * 24 * 60)
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours} hr {minutes} min"
    if measure == "first_attempt_rate_percent":
        if isinstance(value, float) and value == int(value):
            return f"{int(value)}%"
        return f"{value}%"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _build_model_time_split(metrics: dict):
    """Read the sprint-metrics' model_time_split null-tolerantly.

    Returns None when the field is absent or null (the pinned 3.0.0 package
    carries it as null for every sprint). Otherwise returns a dict with
    planning_minutes, building_minutes and the two segment widths as
    percentages of the bar.
    """
    split = metrics.get("model_time_split")
    if not isinstance(split, dict):
        return None
    planning = split.get("refinement")
    building = split.get("delivery")
    if planning is None or building is None:
        return None
    total = planning + building
    if total == 0:
        return {
            "planning_minutes": planning,
            "building_minutes": building,
            "planning_percent": 0,
            "building_percent": 100,
        }
    return {
        "planning_minutes": planning,
        "building_minutes": building,
        "planning_percent": int(round(planning / total * 100)),
        "building_percent": int(round(building / total * 100)),
    }


def _build_idle_time(metrics: dict):
    """Read the sprint-metrics' idle figure null-tolerantly.

    Returns None when the field is absent or null, or when idle_minutes is
    null (the pinned 3.0.0 package carries it as null for every sprint).
    Otherwise returns a dict with idle_minutes, sprint_total_minutes and the
    idle share of the sprint's total time as a percentage.
    """
    idle = metrics.get("idle")
    if not isinstance(idle, dict):
        return None
    idle_minutes = idle.get("idle_minutes")
    if idle_minutes is None:
        return None
    sprint_total = idle.get("sprint_duration_minutes")
    if sprint_total is None:
        return None
    if sprint_total == 0:
        return {
            "idle_minutes": idle_minutes,
            "sprint_total_minutes": sprint_total,
            "idle_percent": 0,
        }
    return {
        "idle_minutes": idle_minutes,
        "sprint_total_minutes": sprint_total,
        "idle_percent": int(round(idle_minutes / sprint_total * 100)),
    }


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
        "points_delivered": "points delivered",
        "throughput": "stories delivered",
        "blocked_aging_days": "days blocked",
        "superseded_count": "stories superseded",
        "crew_fixes_merged": "crew fixes merged",
        "wip_violations": "WIP violations",
    }
    return LABELS.get(measure, measure)


def _changed_from_metrics(metrics: dict, prior: dict) -> list[dict]:
    """Build 'What changed' entries from sprint-metrics answers when analysis is absent.

    Compares each measure's current value to its prior value and returns
    entries for measures that have a non-null value in both.
    """
    MEASURES = [
        "cycle_time_minutes",
        "lead_time_minutes",
        "throughput",
        "points_delivered",
        "first_attempt_rate_percent",
        "wip_violations",
        "blocked_aging_days",
        "superseded_count",
    ]
    entries = []
    for measure in MEASURES:
        now_value = metrics.get(measure)
        prev_value = prior.get(measure)
        if now_value is None or prev_value is None:
            continue
        entries.append(
            {
                "text": "",
                "label": _changed_label(measure),
                "previous": _format_metrics_value(measure, prev_value),
                "now": _format_metrics_value(measure, now_value),
            }
        )
    return entries


CAUSE_LABELS = {
    "test_assertion_failed": "A test's assertion failed",
    "already_exists": '"already exists"',
    "must_create_or_edit_file": "Must create or edit a file",
    "undefined_name": "Undefined name (lint)",
    "no_test_written": "No test written",
    "unrecorded": "Cause not recorded",
}

# Board's own word for each step the flow records.
STEP_DISPLAY = {
    "sponsor": "the sponsor",
    "decompose": "decomposition",
    "refinement": "refinement",
    "story_problem": "the story's problem",
    "split": "the split",
    "criteria_check": "criteria check",
    "build": "building",
    "gate": "the checks",
    "ci": "CI",
    "review": "review",
    "deploy_review": "deploy review",
    "qa": "QA",
    "merge": "merge",
    "main": "main",
    "release_check": "release check",
    "revert": "revert",
    "revisit": "revisit",
    "design": "design",
}

# Rule codes as plain-sentence fragments. The fragment completes the sentence
# "X <fragment>, so back to Y" where X is the sent_from step's display word.
RULE_FRAGMENTS = {
    "gate.findings_at_done": "found problems at done",
    "gate.merge_changes_requested": "asked for changes",
    "gate.ci_before_review": "found problems",
    "gate.review_changes_requested": "asked for changes",
    "gate.criteria_repair": "found conflicts",
    "gate.design_refused": "was refused at",
}


def _step_display(step: str) -> str:
    """A step's display word; an unknown step reads as a step, not a code."""
    if step in STEP_DISPLAY:
        return STEP_DISPLAY[step]
    return step.replace("_", " ") if step else ""


def _sent_back_sentence(event: dict) -> str:
    """A plain sentence for a send-back row, naming the steps in the board's words."""
    rule = event.get("rule", "")
    sent_from = _step_display(event.get("sent_from", ""))
    sent_to = _step_display(event.get("sent_to", ""))
    card = event.get("card")

    fragment = RULE_FRAGMENTS.get(rule)
    if fragment:
        if fragment == "was refused at":
            # No-card design send-back: "A design was refused at <sent_from>"
            sentence = f"A design was refused at {sent_from}"
        else:
            sentence = f"{sent_from} {fragment}"
    else:
        sentence = f"{sent_from} sent it back"

    if sent_to:
        sentence += f", so back to {sent_to}"
    return sentence


def _build_sent_back_rows(events: list[dict]) -> list[dict]:
    """One row per sent_back event, ready to render in the sprint's 'Sent back' card."""
    rows = []
    for event in events:
        if event.get("kind") != "sent_back":
            continue
        card = event.get("card")
        rows.append(
            {
                "card_number": card.get("number") if card else None,
                "sentence": _sent_back_sentence(event),
                "time": _format_event_time(event.get("at", "")),
            }
        )
    return rows


def _parse_iso_timestamp(at: str) -> datetime | None:
    """Parse an ISO 8601 timestamp to a UTC datetime; None when unparseable."""
    if not at:
        return None
    try:
        return datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_left_open_duration(seconds: float) -> str:
    """A duration in seconds as the left-open card's own words: 'for 2 days', 'for 1 hour', 'for 30 min'."""
    if seconds <= 0:
        return "for 0 min"
    total_minutes = round(seconds / 60)
    if total_minutes < 60:
        return f"for {total_minutes} min"
    total_hours = total_minutes // 60
    if total_hours < 24:
        return f"for {total_hours} hour{'s' if total_hours != 1 else ''}"
    total_days = total_hours // 24
    return f"for {total_days} day{'s' if total_days != 1 else ''}"


def _left_open_rows(
    events: list[dict], cards: list[dict], sprint: dict
) -> list[dict]:
    """Rows for the sprint's 'Left open at the end' card.

    Replays the board from the sprint's events alone: each story's column at
    the sprint's end is the to_column of its last card_moved (or move) event
    that carries a non-null to_column. A story whose end-of-sprint column is
    not Done gets a row with a badge (Blocked, Refused or Waiting), its
    repository, number, title, and how long it has been in that state.
    Epics and Goals are excluded.
    """
    # Card types: only "Story" cards get rows
    card_types: dict[tuple, str] = {}
    cards_by_key: dict[tuple, dict] = {}
    for card in cards:
        key = (card.get("repo"), card.get("number"))
        card_types[key] = card.get("type", "")
        cards_by_key[key] = card

    # Collect sent_back keys for identifying send-back moves:
    # (repo, number, at_truncated_to_seconds)
    sent_back_keys: set[tuple] = set()
    for event in events:
        if event.get("kind") == "sent_back":
            card_ref = event.get("card")
            if card_ref:
                at_sec = event.get("at", "")[:19]
                sent_back_keys.add(
                    (card_ref.get("repo"), card_ref.get("number"), at_sec)
                )

    # Replay the board: track each card's last move into a column
    card_state: dict[tuple, dict] = {}
    for event in events:
        if event.get("kind") not in ("card_moved", "move"):
            continue
        card_ref = event.get("card")
        if not card_ref:
            continue
        to_col = event.get("to_column")
        if not to_col:
            continue
        key = (card_ref.get("repo"), card_ref.get("number"))
        at_sec = event.get("at", "")[:19]
        is_sent_back = (
            card_ref.get("repo"),
            card_ref.get("number"),
            at_sec,
        ) in sent_back_keys
        card_state[key] = {
            "column": to_col,
            "moved_at": event.get("at", ""),
            "moved_by_sent_back": is_sent_back,
        }

    # The sprint's end as a UTC datetime: midnight of the day after the end date
    end_date = sprint.get("end", "")
    try:
        from datetime import timezone

        sprint_end_dt = (
            datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            + timedelta(days=1)
        )
    except ValueError:
        return []

    rows = []
    for key, state in card_state.items():
        if state["column"] == "Done":
            continue
        if card_types.get(key, "") != "Story":
            continue

        repo, number = key
        card = cards_by_key.get(key, {})
        title = card.get("title", "")

        # Badge per R34
        if state["column"] == "Blocked":
            badge_label = "Blocked"
            badge_tone = "blocked"
        elif state["moved_by_sent_back"]:
            badge_label = "Refused"
            badge_tone = "blocked"
        else:
            badge_label = "Waiting"
            badge_tone = "waiting"

        # Duration: from the last move into this column to the sprint's end
        moved_dt = _parse_iso_timestamp(state["moved_at"])
        if moved_dt:
            duration_seconds = (sprint_end_dt - moved_dt).total_seconds()
        else:
            duration_seconds = 0.0
        duration = _format_left_open_duration(duration_seconds)

        rows.append(
            {
                "repo": repo,
                "number": number,
                "title": title,
                "badge_label": badge_label,
                "badge_tone": badge_tone,
                "duration": duration,
            }
        )

    rows.sort(key=lambda r: (r["repo"] or "", r["number"] or 0))
    return rows


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


def _load_all_events(pkg: Path, index: dict) -> list[dict]:
    """Load all events from all period files in the package."""
    periods = index.get("periods", [])
    events: list[dict] = []
    for period in periods:
        events_file = pkg / period["file"]
        if events_file.is_file():
            data = _load_json(events_file)
            events.extend(data.get("events", []))
    return events


def _decided_from_events_and_cards(
    events: list[dict], cards: list[dict], sprint: dict
) -> list[dict]:
    """Compute the crew's decisions from events and cards when analysis is absent."""
    decided: list[dict] = []
    start = sprint["start"]
    end = sprint["end"]
    for event in events:
        if event.get("kind") == "pull_merged" and event.get("design_revision"):
            decided.append(
                {
                    "at": event["at"],
                    "kind": "design_revision",
                    "number": event["number"],
                    "repo": event["repo"],
                }
            )
    for card in cards:
        if card.get("type") == "Epic" and card.get("technical"):
            created = card.get("created", "")
            if created and start <= created[:10] <= end:
                decided.append(
                    {
                        "at": created,
                        "kind": "technical_epic",
                        "number": card["number"],
                        "repo": card["repo"],
                    }
                )
    decided.sort(key=lambda d: d["at"])
    return decided


def _filter_events_by_card(
    events: list[dict], card_number, card_repo: str
) -> list[dict]:
    """Filter events to those for a specific card, sorted by timestamp."""
    card_events = []
    for e in events:
        card_ref = e.get("card")
        if not card_ref:
            continue
        if card_ref.get("number") == card_number and card_ref.get("repo") == card_repo:
            card_events.append(e)
    card_events.sort(key=lambda e: e.get("at", ""))
    return card_events


def _format_event_time(at: str, include_date: bool = False) -> str:
    """Format an ISO timestamp like '2026-10-01T09:15:00+00:00' for the timeline.

    Returns 'HH:MM', or 'Mon D, HH:MM' when include_date is True.
    """
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", at)
    if match:
        month = _MONTHS[int(match.group(2)) - 1]
        day = int(match.group(3))
        clock = f"{match.group(4)}:{match.group(5)}"
        if include_date:
            return f"{month} {day}, {clock}"
        return clock
    return at


def _format_event_description(event: dict) -> str | None:
    """A human-readable description of an event for the timeline.

    Returns None for internal per-tool or per-turn events that are omitted
    from the journey timeline.
    """
    kind = event.get("kind", "")
    if kind in _OMITTED_EVENT_KINDS:
        return None
    to_column = event.get("to_column")
    from_column = event.get("from_column")
    if to_column and (kind == "move" or kind == "card_moved"):
        return f"Moved to {to_column}"
    if kind == "work_started":
        role = event.get("role", "")
        return f"Work started by {role}" if role else "Work started"
    if kind == "work_finished":
        role = event.get("role", "")
        verdict = event.get("verdict")
        if verdict:
            return f"Work finished by {role}: {verdict.replace('_', ' ')}"
        return f"Work finished by {role}" if role else "Work finished"
    if kind == "gate_checked":
        return "Checks passed" if event.get("passed") else "Checks failed"
    if kind == "session_started":
        return "Session started"
    if kind == "session_ended":
        return "Session ended"
    if kind == "attempt":
        number = event.get("number")
        return f"Attempt {number}" if number else "Attempt"
    if kind == "blocked":
        return "Blocked"
    if kind == "escalated":
        return "Escalated"
    if kind == "returned":
        reason = event.get("reason")
        return f"Returned: {reason}" if reason else "Returned"
    if kind == "sent_back":
        sent_to = event.get("sent_to")
        return f"Sent back to {sent_to}" if sent_to else "Sent back"
    # Fallback: humanize the kind (replace underscores with spaces, capitalise)
    return kind.replace("_", " ").capitalize() if kind else "Event"


def _build_board_state(
    pkg: Path,
    index: dict,
    sprint_name: str,
) -> tuple[list[str], dict[str, list[dict]]]:
    """Compute the board's columns and place each card in its initial column.

    Returns (columns, board_cards) where columns is an ordered list of column
    names and board_cards maps each column name to a list of card dicts with
    'link_text', 'link_url' and 'title' keys.
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
            "link_text": f"{display_repo}#{number}",
            "link_url": url,
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
