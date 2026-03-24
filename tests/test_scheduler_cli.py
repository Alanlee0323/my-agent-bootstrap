from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def _run_scheduler(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    scheduler = repo_root / "skill_scheduler.py"
    command = [sys.executable, str(scheduler), *args]
    merged_env = None
    if env is not None:
        merged_env = dict(os.environ)
        merged_env.update(env)
    return subprocess.run(command, capture_output=True, text=True, check=False, env=merged_env)


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


def test_scheduler_warns_when_generated_artifacts_are_stale(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skills_repo = tmp_path / "my-agent-skills"
    project_root = tmp_path / "target-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "skill_scheduler.py").write_text("# placeholder", encoding="utf-8")
    (skills_repo / "planning").mkdir(parents=True, exist_ok=True)
    (skills_repo / "planning" / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: planning-implementation",
                "description: Shared planning helper",
                "---",
                "",
                "## When to use this skill",
                "- use planning-implementation",
            ]
        ),
        encoding="utf-8",
    )
    (skills_repo / "bundles").mkdir(parents=True, exist_ok=True)
    (skills_repo / "bundles" / "engineer.yaml").write_text(
        "name: engineer\nskills:\n  - planning-implementation\n",
        encoding="utf-8",
    )
    (skills_repo / "policies").mkdir(parents=True, exist_ok=True)
    (skills_repo / "policies" / "base.yaml").write_text(
        "default_max_skill_reads: 3\n",
        encoding="utf-8",
    )
    profile_path = project_root / "agent.profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "name: engineer-codex",
                "bundle: engineer",
                "agent: codex",
                "adapter_output: .agent",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "apply_agent_profile.py"),
            "--profile",
            str(profile_path),
            "--project-root",
            str(project_root),
            "--default-skills-repo",
            str(skills_repo),
            "--template-root",
            str(repo_root / "adapters"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    (project_root / "skills" / "engineer").mkdir(parents=True, exist_ok=True)
    (project_root / "skills" / "engineer" / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: local-station-debug",
                "description: Project-only station debugging",
                "---",
                "",
                "## When to use this skill",
                "- use local-station-debug",
            ]
        ),
        encoding="utf-8",
    )

    env = {"PYTHONPATH": str(repo_root), "AGENT_BOOTSTRAP_ROOT": str(project_root)}
    json_completed = _run_scheduler("--status", "--format", "json", env=env)
    assert json_completed.returncode == 0, json_completed.stderr
    payload = json.loads(json_completed.stdout)
    assert payload["artifact_freshness"]["available"] is True
    assert payload["artifact_freshness"]["is_stale"] is True

    text_completed = _run_scheduler("--status", "--format", "text", env=env)
    assert text_completed.returncode == 0, text_completed.stderr
    assert "Generated agent artifacts are stale" in text_completed.stdout
