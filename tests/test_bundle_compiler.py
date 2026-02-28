from __future__ import annotations

import json
import os
from pathlib import Path
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compile_bundle import compile_bundle_for_agents


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


def test_compile_bundle_generates_prompt_with_contracts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skills_repo = tmp_path / "my-agent-skills"
    project_root = tmp_path / "target-project"
    output_root = tmp_path / "out"

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
                "description: Engineering bundle",
                "skills:",
                "  - planning-implementation",
                "  - handling-review",
                "policy_overrides:",
                "  output_language: zh-TW",
                "  max_skill_reads: 4",
            ]
        ),
        encoding="utf-8",
    )
    (skills_repo / "policies").mkdir(parents=True, exist_ok=True)
    (skills_repo / "policies" / "base.yaml").write_text(
        "\n".join(
            [
                "require_scheduler_for_complex_tasks: true",
                "require_json_output: true",
                "max_scheduler_retries: 2",
                "default_max_skill_reads: 3",
            ]
        ),
        encoding="utf-8",
    )

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "skill_scheduler.py").write_text("# placeholder", encoding="utf-8")

    written = compile_bundle_for_agents(
        adapters=["codex"],
        bundle_name="engineer",
        skills_repo=skills_repo,
        output_root=output_root,
        project_root=project_root,
        template_root=repo_root / "adapters",
    )

    assert written
    prompt_path = output_root / "codex" / "engineer" / "AGENTS.generated.md"
    ir_path = output_root / "codex" / "engineer" / "ir.json"
    assert prompt_path.exists()
    assert ir_path.exists()

    prompt_text = prompt_path.read_text(encoding="utf-8")
    assert "Intent Whitelist" in prompt_text
    assert "planning-implementation" in prompt_text
    assert "handling-review" in prompt_text
    assert "stdout" in prompt_text
    assert "stderr" in prompt_text
    assert str((project_root / "skill_scheduler.py").resolve()) in prompt_text

    ir_payload = json.loads(ir_path.read_text(encoding="utf-8"))
    assert ir_payload["intent_enum"] == ["planning-implementation", "handling-review"]
    assert ir_payload["retry_policy"]["max_retries"] == 2


def test_compile_bundle_fails_on_missing_skill(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skills_repo = tmp_path / "my-agent-skills"
    project_root = tmp_path / "target-project"
    output_root = tmp_path / "out"

    _write_skill(
        skills_repo / "planning" / "SKILL.md",
        name="planning-implementation",
        description="Plan implementation steps",
    )
    (skills_repo / "bundles").mkdir(parents=True, exist_ok=True)
    (skills_repo / "bundles" / "broken.yaml").write_text(
        "\n".join(
            [
                "name: broken",
                "skills:",
                "  - planning-implementation",
                "  - missing-skill",
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

    try:
        compile_bundle_for_agents(
            adapters=["codex"],
            bundle_name="broken",
            skills_repo=skills_repo,
            output_root=output_root,
            project_root=project_root,
            template_root=repo_root / "adapters",
        )
    except ValueError as exc:
        assert "missing skill" in str(exc)
    else:
        raise AssertionError("Expected missing skill validation error.")
