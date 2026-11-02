"""Scratch: verify test_build_check_exits_zero's AC1 branch on a no-analysis pin."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / ".package"
DELIVERY_HISTORY_TAG = REPO_ROOT / "delivery-history.tag"


def test_ac1_branch_on_no_analysis_pin():
    tag = "delivery-history-SCRATCH-3"
    pkg_dir = PACKAGE_DIR / tag
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "3.0.0", "package": "delivery-history", "date": "2026-11-06"}
        )
    )
    (pkg_dir / "manifest.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]})
    )
    (pkg_dir / "schema.json").write_text(json.dumps({"type": "object"}))
    (pkg_dir / "events.schema.json").write_text(json.dumps({"type": "object"}))

    index = {
        "package": "delivery-history",
        "schema_version": "3.0.0",
        "date": "2026-11-06",
        "timezone": "America/Chicago",
        "crew_repository": "crew",
        "repositories": ["crew-presentation"],
        "sprints": [
            {"name": "Sprint 1", "start": "2026-11-06", "end": "2026-11-06"}
        ],
        "cards": [
            {
                "repo": "crew-presentation",
                "number": 1,
                "type": "Story",
                "title": "A test story",
                "url": "https://github.com/mqucifer/crew-presentation/issues/1",
                "parent": None,
                "points": 1,
                "sprint": "Sprint 1",
                "status": "Done",
                "status_set": "2026-11-06T12:00:00Z",
                "created": "2026-11-06T09:00:00Z",
                "closed": "2026-11-06T12:00:00Z",
                "technical": False,
                "closed_as": "completed",
                "superseded_because": None,
            }
        ],
        "periods": [
            {
                "sprint": "Sprint 1",
                "start": "2026-11-06",
                "end": "2026-11-06",
                "file": "events/2026-11-06.json",
                "events": 1,
            }
        ],
        "sprint_metrics": {
            "release": "3.0.0",
            "answers": {
                "Sprint 1": {
                    "cycle_time_days": 0,
                    "lead_time_days": 0,
                    "throughput": 1,
                    "wip_violations": 0,
                    "blocked_aging_days": 0,
                    "escalation_rate_percent": 0,
                    "points_delivered": 1,
                    "first_attempt_numerator": 1,
                    "first_attempt_denominator": 1,
                    "escalation_count": 0,
                    "superseded_count": 0,
                    "superseded_points": 0,
                    "first_attempt_rate_percent": 100,
                    "failure_breakdown": [],
                    "top_failure_causes": {},
                    "superseded_breakdown": None,
                    "flags": None,
                    "prior": None,
                    "delta": None,
                    "cycle_time_minutes": 30,
                    "lead_time_minutes": 30,
                    "roster": {"completed_stories": ["crew-presentation#1"]},
                }
            },
        },
    }
    (pkg_dir / "delivery-history.json").write_text(json.dumps(index))

    events_dir = pkg_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / "2026-11-06.json").write_text(
        json.dumps(
            {
                "events": [
                    {
                        "at": "2026-11-06T09:00:00Z",
                        "card": {"repo": "crew-presentation", "number": 1},
                        "from_column": "Inbox (Goals)",
                        "to_column": "Sprint Backlog",
                    }
                ]
            }
        )
    )

    original_tag = DELIVERY_HISTORY_TAG.read_text()
    DELIVERY_HISTORY_TAG.write_text(tag + "\n")

    try:
        result = subprocess.run(
            [sys.executable, "build.py"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, (
            f"build.py failed for no-analysis package:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        build_dir = REPO_ROOT / "build"
        page = (build_dir / "sprint-1.html").read_text()
        # Mirror the AC1 branch of test_build_check_exits_zero.
        assert "The Architect's split, story by story" in page
        assert 'class="story-list"' in page, "story list not found"
        assert 'class="attempt-legend"' not in page, "attempt legend found without analysis"
        assert 'class="attempt-row"' not in page, "attempt rows found without analysis"
        assert 'class="attempt-block' not in page, "attempt blocks found without analysis"
    finally:
        DELIVERY_HISTORY_TAG.write_text(original_tag)
        shutil.rmtree(pkg_dir, ignore_errors=True)
