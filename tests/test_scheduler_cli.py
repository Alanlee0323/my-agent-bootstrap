from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _run_scheduler(*args: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    scheduler = repo_root / "skill_scheduler.py"
    command = [sys.executable, str(scheduler), *args]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_scheduler_requires_context_when_whitelist_is_set() -> None:
    completed = _run_scheduler(
        "--task",
        "health check",
        "--intent-whitelist",
        "planning-implementation,handling-review",
        "--format",
        "json",
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["error"]["code"] == "invalid_intent"


def test_scheduler_rejects_context_outside_whitelist() -> None:
    completed = _run_scheduler(
        "--task",
        "health check",
        "--context",
        "deploy-to-prod",
        "--intent-whitelist",
        "planning-implementation,handling-review",
        "--format",
        "json",
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["error"]["code"] == "invalid_intent"
    assert "whitelist" in payload["error"]["message"]

