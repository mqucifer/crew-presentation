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

SUPPORTED_MAJOR_VERSIONS = (1,)

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
    """Render each page: one per sprint, plus the other views."""
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

        stories = []
        for story in analysis_stories:
            card_key = (story["card"]["number"], story["card"]["repo"])
            card = cards_by_key.get(card_key)
            if card and card.get("sprint") == sprint["name"]:
                raw_blocks = story.get("blocks", [])
                delivered = story.get("delivered", False)
                if isinstance(raw_blocks, int):
                    if delivered:
                        blocks = ["refused"] * (raw_blocks - 1) + ["landed"]
                    else:
                        blocks = ["refused"] * raw_blocks
                elif raw_blocks:
                    blocks = list(raw_blocks)
                else:
                    blocks = []
                stories.append(
                    {
                        "number": story["card"]["number"],
                        "title": card.get("title", ""),
                        "blocks": blocks,
                        "crew_fixes": story.get("crew_fixes", []),
                        "delivered": delivered,
                    }
                )

        context = {
            "sprints": sprints,
            "sprint": sprint,
            "metrics": metrics,
            "sprint_slug": slug,
            "stories": stories,
            "failure_causes": _build_failure_causes(metrics),
        }
        pages[slug] = sprint_template.render(**context)

    for template_name, output_name in TEMPLATE_MAP.items():
        template = env.get_template(template_name)
        pages[output_name] = template.render(
            manifest=manifest, package=index, sprint_slug=""
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
        (BUILD_DIR / name).write_text(content)

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

    Each row carries the reason, its count, the bar's width as a percentage of
    the largest count, and whether the reason is the 'Cause not recorded'
    placeholder. Widths are computed here (display sizing, not a metric) so the
    template only prints values and the build never divides by zero.
    """
    causes = _normalize_failure_causes(metrics.get("top_failure_causes"))
    max_count = max((c["count"] for c in causes), default=0)
    return [
        {
            "reason": c["reason"],
            "count": c["count"],
            "width": int(round(c["count"] / max_count * 100)) if max_count else 0,
            "unrecorded": c["reason"] == "Cause not recorded",
        }
        for c in causes
    ]


if __name__ == "__main__":
    main()
