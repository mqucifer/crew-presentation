"""Setup entry point. Stub until #50 implements the real setup."""
import subprocess
import re
import sys
from pathlib import Path


def main():
    """Install Python dependencies from requirements.txt.

    The lockfile pins exact versions with --hash; the hashes are verified
    by the test suite (test_skeleton.py). Here we install the pinned
    versions so the sandbox has the packages the checks need.
    """
    requirements = Path(__file__).resolve().parent.parent / "requirements.txt"
    packages = []
    for line in requirements.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"([a-zA-Z][a-zA-Z0-9_-]*==\S+)", line)
        if match:
            packages.append(match.group(1))
    if packages:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *packages],
        )
    print("crew-presentation: dependencies installed")
    return 0


if __name__ == "__main__":
    main()
