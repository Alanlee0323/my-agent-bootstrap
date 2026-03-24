from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_skill(path: Path, name: str, description: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                "",
                "## When to use this skill",
                f"- use {name}",
            ]
        ),
        encoding="utf-8",
    )


def test_bootstrap_status_explain_reports_policy_and_skill_sources(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skills_repo = tmp_path / "my-agent-skills"
    project_root = tmp_path / "target-project"

    _write_skill(
        skills_repo / "planning" / "SKILL.md",
        name="planning-implementation",
        description="Global planning description",
    )
    _write_skill(
        skills_repo / "review" / "SKILL.md",
        name="handling-review",
        description="Global review description",
    )
    (skills_repo / "bundles").mkdir(parents=True, exist_ok=True)
    (skills_repo / "bundles" / "engineer.yaml").write_text(
        "\n".join(
            [
                "name: engineer",
                "skills:",
                "  - planning-implementation",
                "  - handling-review",
                "policy_overrides:",
                "  max_skill_reads: 2",
            ]
        ),
        encoding="utf-8",
    )
    (skills_repo / "policies").mkdir(parents=True, exist_ok=True)
    (skills_repo / "policies" / "base.yaml").write_text(
        "default_max_skill_reads: 1\n",
        encoding="utf-8",
    )

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "skill_scheduler.py").write_text("# placeholder", encoding="utf-8")
    _write_skill(
        project_root / "skills" / "planning" / "SKILL.md",
        name="planning-implementation",
        description="Local planning override",
    )
    _write_skill(
        project_root / "skills" / "engineer" / "SKILL.md",
        name="local-station-debug",
        description="Project-only station debugging",
    )
    (project_root / "bundles.local").mkdir(parents=True, exist_ok=True)
    (project_root / "bundles.local" / "engineer.yaml").write_text(
        "\n".join(
            [
                "extends: engineer",
                "add_skills:",
                "  - local-station-debug",
                "remove_skills:",
                "  - handling-review",
                "policy_overrides:",
                "  max_skill_reads: 5",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "bootstrap_status.py"),
            "--bundle",
            "Engineer",
            "--skills-repo",
            str(skills_repo),
            "--project-root",
            str(project_root),
            "--format",
            "json",
            "--explain",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["bundle"]["name"] == "engineer"
    assert payload["provenance"]["policies"]["max_skill_reads"]["winner"]["layer"] == "bundle.local"
    assert payload["provenance"]["skill_definitions"]["planning-implementation"]["layer"] == "local"
    assert payload["provenance"]["bundle_membership"]["local-station-debug"]["layer"] == "bundle.local"


def test_bootstrap_status_profile_mode_tracks_profile_override(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skills_repo = tmp_path / "my-agent-skills"
    project_root = tmp_path / "target-project"

    _write_skill(
        skills_repo / "planning" / "SKILL.md",
        name="planning-implementation",
        description="Plan implementation steps",
    )
    (skills_repo / "bundles").mkdir(parents=True, exist_ok=True)
    (skills_repo / "bundles" / "engineer.yaml").write_text(
        "\n".join(
            [
                "name: engineer",
                "skills:",
                "  - planning-implementation",
                "policy_overrides:",
                "  max_skill_reads: 2",
            ]
        ),
        encoding="utf-8",
    )
    (skills_repo / "policies").mkdir(parents=True, exist_ok=True)
    (skills_repo / "policies" / "base.yaml").write_text(
        "default_max_skill_reads: 1\n",
        encoding="utf-8",
    )

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "skill_scheduler.py").write_text("# placeholder", encoding="utf-8")
    profile_path = project_root / "agent.profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "name: engineer-codex",
                "bundle: Engineer",
                "agent: codex",
                "max_skill_reads: 6",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "bootstrap_status.py"),
            "--profile",
            str(profile_path),
            "--project-root",
            str(project_root),
            "--default-skills-repo",
            str(skills_repo),
            "--format",
            "json",
            "--explain",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    trace = payload["provenance"]["policies"]["max_skill_reads"]
    assert trace["value"] == 6
    assert trace["winner"]["layer"] == "profile"
    assert [entry["layer"] for entry in trace["sources"]] == ["bundle", "profile"]
