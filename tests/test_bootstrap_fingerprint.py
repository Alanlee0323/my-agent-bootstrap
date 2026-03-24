from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bootstrap_fingerprint import compute_input_fingerprint, detect_artifact_freshness


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


def test_compute_input_fingerprint_changes_when_project_inputs_change(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    skills_repo = tmp_path / "my-agent-skills"
    profile_path = project_root / "agent.profile.yaml"
    project_root.mkdir(parents=True, exist_ok=True)
    _write_skill(
        project_root / "skills" / "engineer" / "SKILL.md",
        name="local-station-debug",
        description="Project-only station debugging",
    )
    (project_root / "bundles.local").mkdir(parents=True, exist_ok=True)
    (project_root / "bundles.local" / "engineer.yaml").write_text(
        "extends: engineer\nadd_skills:\n  - local-station-debug\n",
        encoding="utf-8",
    )
    profile_path.write_text("name: engineer\nbundle: engineer\nagent: codex\n", encoding="utf-8")
    _write_skill(
        skills_repo / "skills" / "shared" / "SKILL.md",
        name="planning-implementation",
        description="Shared planning helper",
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
    git_dir = skills_repo / ".git"
    (git_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "refs" / "heads" / "main").write_text("abc123def456\n", encoding="utf-8")

    before = compute_input_fingerprint(
        project_root=project_root,
        skills_repo=skills_repo,
        profile_path=profile_path,
    )
    assert before["skills_repo_git_sha"] == "abc123def456"

    (project_root / "bundles.local" / "engineer.yaml").write_text(
        "extends: engineer\nadd_skills:\n  - local-station-debug\n  - extra-local-skill\n",
        encoding="utf-8",
    )
    after = compute_input_fingerprint(
        project_root=project_root,
        skills_repo=skills_repo,
        profile_path=profile_path,
    )

    assert before["digest"] != after["digest"]


def test_detect_artifact_freshness_reports_stale_when_manifest_digest_is_old(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    skills_repo = project_root / "my-agent-skills"
    output_root = project_root / ".agent"
    profile_path = project_root / "agent.profile.yaml"
    project_root.mkdir(parents=True, exist_ok=True)
    _write_skill(
        project_root / "skills" / "engineer" / "SKILL.md",
        name="local-station-debug",
        description="Project-only station debugging",
    )
    _write_skill(
        skills_repo / "skills" / "shared" / "SKILL.md",
        name="planning-implementation",
        description="Shared planning helper",
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
    profile_path.write_text("name: engineer\nbundle: engineer\nagent: codex\n", encoding="utf-8")
    output_root.mkdir(parents=True, exist_ok=True)

    current = compute_input_fingerprint(
        project_root=project_root,
        skills_repo=skills_repo,
        profile_path=profile_path,
    )
    stored = dict(current)
    stored["digest"] = "stale-digest"
    (output_root / "profile.manifest.json").write_text(
        json.dumps(
            {
                "profile_path": "agent.profile.yaml",
                "project_root": ".",
                "skills_repo": "my-agent-skills",
                "bundle": "engineer",
                "agents": ["codex"],
                "adapter_output": ".agent",
                "input_fingerprint": stored,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    freshness = detect_artifact_freshness(project_root)

    assert freshness["available"] is True
    assert freshness["is_stale"] is True
    assert freshness["manifest_kind"] == "profile"
