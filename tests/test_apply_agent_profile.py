from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.apply_agent_profile import load_profile


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


def test_load_profile_parses_agent_and_defaults(tmp_path: Path) -> None:
    profile_path = tmp_path / "agent.profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "name: engineer-codex",
                "bundle: engineer",
                "agent: codex",
                "adapter_output: .agent",
                "max_skill_reads: 3",
            ]
        ),
        encoding="utf-8",
    )

    profile = load_profile(profile_path)
    assert profile.name == "engineer-codex"
    assert profile.bundle == "engineer"
    assert profile.agents == ["codex"]
    assert profile.adapter_output == ".agent"
    assert profile.max_skill_reads == 3
    assert profile.generate_launchers is True


def test_apply_profile_generates_manifest_and_launchers(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skills_repo = tmp_path / "my-agent-skills"
    project_root = tmp_path / "target-project"

    _write_skill(
        skills_repo / "planning" / "SKILL.md",
        name="planning-implementation",
        description="Plan implementation steps",
    )
    _write_skill(
        skills_repo / "review" / "SKILL.md",
        name="handling-review",
        description="Review and risk control",
    )
    (skills_repo / "bundles").mkdir(parents=True, exist_ok=True)
    (skills_repo / "bundles" / "engineer.yaml").write_text(
        "\n".join(
            [
                "name: engineer",
                "skills:",
                "  - planning-implementation",
                "  - handling-review",
            ]
        ),
        encoding="utf-8",
    )
    (skills_repo / "policies").mkdir(parents=True, exist_ok=True)
    (skills_repo / "policies" / "base.yaml").write_text(
        "require_scheduler_for_complex_tasks: true\n",
        encoding="utf-8",
    )

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "skill_scheduler.py").write_text("# placeholder", encoding="utf-8")

    profile_path = project_root / "agent.profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "name: engineer-multi",
                "bundle: engineer",
                "agents:",
                "  - codex",
                "  - gemini",
                "adapter_output: .agent",
                "generate_launchers: true",
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
    manifest_path = project_root / ".agent" / "profile.manifest.json"
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["bundle"] == "engineer"
    assert payload["agents"] == ["codex", "gemini"]

    launchers_dir = project_root / ".agent" / "launchers"
    assert (launchers_dir / "launch_codex.bat").exists()
    assert (launchers_dir / "launch_gemini.sh").exists()

