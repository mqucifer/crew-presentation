"""Setup: install dependencies and fetch the package and design-system CSS.

This is the only code that touches the network (§19.6: failure is loud).
It runs in the sandbox's setup phase, before any check.
"""

import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / ".package"
LOCKFILE = REPO_ROOT / "uv.lock"
DELIVERY_HISTORY_TAG = REPO_ROOT / "delivery-history.tag"
DESIGN_SYSTEM_VERSION_FILE = REPO_ROOT / "site" / "css" / "design-system.version"

CREW_REPO = "mqucifer/crew"
JSDELIVR_BASE = "https://cdn.jsdelivr.net/gh/mqucifer/design-system"


def _uv() -> str:
    """The uv executable, installed via pip into the user site if the image lacks it."""
    found = shutil.which("uv")
    if found is not None:
        return found
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--user", "--quiet", "uv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Failed to install uv:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")


def _sync_dependencies() -> None:
    """Install the Python dependencies pinned in uv.lock into the user site.

    The checks run bare `python` (the image's own), which does not see a
    virtual environment. So uv exports the lockfile, with its hashes, and pip
    installs exactly those pins with --user: packages land under
    $HOME/.local/lib/python3.12/site-packages/, visible to every check.

    It locks first: only setup runs uv, so a dependency changed in
    pyproject.toml is locked here, and the lock it writes is committed with the
    change. With nothing changed, `uv lock` keeps every pin as it is.
    """
    uv = _uv()
    lock = subprocess.run(
        [uv, "lock", "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if lock.returncode != 0:
        print(f"Failed to lock {LOCKFILE}:\n{lock.stderr}", file=sys.stderr)
        sys.exit(1)
    with tempfile.TemporaryDirectory() as tmp:
        requirements = Path(tmp) / "requirements.txt"
        export = subprocess.run(
            [
                uv,
                "export",
                "--frozen",
                "--extra",
                "dev",
                "--no-emit-project",
                "--quiet",
                "--output-file",
                str(requirements),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if export.returncode != 0:
            print(f"Failed to export {LOCKFILE}:\n{export.stderr}", file=sys.stderr)
            sys.exit(1)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--user",
                "--quiet",
                "--require-hashes",
                "--no-deps",
                "-r",
                str(requirements),
            ],
            capture_output=True,
            text=True,
            check=False,
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
    except OSError as exc:
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
        print(
            f"Package index not found after extraction: {index_file}", file=sys.stderr
        )
        sys.exit(1)


def design_system_css(version: str) -> Path:
    """Where setup puts the design-system stylesheet for a pinned tag."""
    return PACKAGE_DIR / f"design-system-{version}.css"


def _download_design_system_css(version: str) -> None:
    """Download the design-system CSS at the pinned tag from jsDelivr."""
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{JSDELIVR_BASE}@{version}/styles.css"
    print(f"Downloading {url}")
    try:
        with urllib.request.urlopen(url) as response:
            design_system_css(version).write_bytes(response.read())
    except OSError as exc:
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
