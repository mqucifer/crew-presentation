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

    manifest = _load_json(pkg / "manifest.json")
    index = _load_json(pkg / "delivery-history.json")
    sprints = index.get("sprints", [])

    pages = {}

    sprint_template = env.get_template("sprint_overview.html")
    for sprint in sprints:
        slug = _slug(sprint["name"])
        context = {
            "manifest": manifest,
            "package": index,
            "sprints": sprints,
            "current_sprint": sprint,
            "sprint_slug": slug,
        }
        pages[slug] = sprint_template.render(**context)

    for template_name, output_name in TEMPLATE_MAP.items():
        template = env.get_template(template_name)
        pages[output_name] = template.render(manifest=manifest, package=index)

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


if __name__ == "__main__":
    main()
