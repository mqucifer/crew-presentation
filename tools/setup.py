"""Setup: install dependencies and fetch the package and design-system CSS.

This is the only code that touches the network (§19.6: failure is loud).
It runs in the sandbox's setup phase, before any check.
"""

import json
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / ".package"
DELIVERY_HISTORY_TAG = REPO_ROOT / "delivery-history.tag"
DESIGN_SYSTEM_VERSION_FILE = REPO_ROOT / "site" / "css" / "design-system.version"
DESIGN_SYSTEM_CSS = PACKAGE_DIR / "design-system.css"

CREW_REPO = "mqucifer/crew"
JSDELIVR_BASE = "https://cdn.jsdelivr.net/gh/mqucifer/design-system"


def _install_uv() -> None:
    """Install uv via pip if it is not already available."""
    if shutil.which("uv") is not None:
        return
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "uv"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to install uv:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def _sync_dependencies() -> None:
    """Install Python dependencies into the user site so bare python can see them.

    The checks run bare `python` (the image's own), which does not see a
    virtual environment. Installing with --user puts packages under
    $HOME/.local/lib/python3.12/site-packages/, visible to every check.
    """
    _install_uv()
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    deps = list(pyproject["project"]["dependencies"])
    dev_deps = pyproject.get("project", {}).get("optional-dependencies", {}).get("dev", [])
    all_deps = deps + dev_deps
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--user", "--quiet"] + all_deps,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to install dependencies:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def _read_release_tag() -> str:
    """Read the delivery-history release tag from the tag file."""
    if not DELIVERY_HISTORY_TAG.is_file():
        print(f"Missing: {DELIVERY_HISTORY_TAG}", file=sys.stderr)
        sys.exit(1)
    tag = DELIVERY_HISTORY_TAG.read_text().strip()
    if not tag:
        print(f"Empty: {DELIVERY_HISTORY_TAG}", file=sys.stderr)
        sys.exit(1)
    return tag


def _read_design_system_version() -> str:
    """Read the pinned design-system tag from the version file."""
    if not DESIGN_SYSTEM_VERSION_FILE.is_file():
        print(f"Missing: {DESIGN_SYSTEM_VERSION_FILE}", file=sys.stderr)
        sys.exit(1)
    version = DESIGN_SYSTEM_VERSION_FILE.read_text().strip()
    if not version:
        print(f"Empty: {DESIGN_SYSTEM_VERSION_FILE}", file=sys.stderr)
        sys.exit(1)
    return version


def _download_delivery_history(tag: str) -> None:
    """Download and extract the delivery-history release asset into .package/."""
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    dest_dir = PACKAGE_DIR / tag
    if dest_dir.is_dir():
        shutil.rmtree(dest_dir)

    # The release asset is a tar.gz at:
    # https://github.com/{owner}/{repo}/releases/download/{tag}/{tag}.tar.gz
    url = f"https://github.com/{CREW_REPO}/releases/download/{tag}/{tag}.tar.gz"
    archive_path = PACKAGE_DIR / f"{tag}.tar.gz"

    print(f"Downloading {url}")
    try:
        with urllib.request.urlopen(url) as response:
            archive_path.write_bytes(response.read())
    except Exception as exc:
        print(f"Failed to download {tag}: {exc}", file=sys.stderr)
        sys.exit(1)

    # Extract: the archive holds one top-level directory named for the tag.
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=PACKAGE_DIR, filter="data")
    except (tarfile.TarError, OSError) as exc:
        print(f"Failed to extract {tag}: {exc}", file=sys.stderr)
        sys.exit(1)

    archive_path.unlink(missing_ok=True)

    # Verify the expected layout
    index_file = dest_dir / "delivery-history.json"
    if not index_file.is_file():
        print(f"Package index not found after extraction: {index_file}", file=sys.stderr)
        sys.exit(1)


def _download_design_system_css(version: str) -> None:
    """Download the design-system CSS at the pinned tag from jsDelivr."""
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{JSDELIVR_BASE}@{version}/styles.css"
    print(f"Downloading {url}")
    try:
        with urllib.request.urlopen(url) as response:
            DESIGN_SYSTEM_CSS.write_bytes(response.read())
    except Exception as exc:
        print(f"Failed to download design-system CSS {version}: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    _sync_dependencies()
    tag = _read_release_tag()
    _download_delivery_history(tag)
    version = _read_design_system_version()
    _download_design_system_css(version)
    print(f"Setup complete: {tag} and design-system {version} in {PACKAGE_DIR}")


if __name__ == "__main__":
    main()
