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
    assert "AGENT_SCHEDULER_PATH" in prompt_text
    assert "AGENT_BOOTSTRAP_ROOT" in prompt_text
    assert "skill_scheduler.py" in prompt_text
    assert str((project_root / "skill_scheduler.py").resolve()) not in prompt_text

    ir_payload = json.loads(ir_path.read_text(encoding="utf-8"))
    assert ir_payload["intent_enum"] == ["planning-implementation", "handling-review"]
    assert ir_payload["retry_policy"]["max_retries"] == 2
    assert ir_payload["runtime"]["scheduler_path"] == "skill_scheduler.py"
    assert ir_payload["runtime"]["bootstrap_root"] == "<project-root>"
    assert ir_payload["provenance"]["skills"]["planning-implementation"]["layer"] == "bundle"
    assert ir_payload["provenance"]["skill_definitions"]["planning-implementation"]["layer"] == "global"
    assert ir_payload["provenance"]["policies"]["max_skill_reads"]["winner"]["layer"] == "bundle"


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


def test_compile_bundle_applies_local_overlay_and_local_skill(tmp_path: Path) -> None:
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
                "  max_skill_reads: 3",
            ]
        ),
        encoding="utf-8",
    )
    (skills_repo / "policies").mkdir(parents=True, exist_ok=True)
    (skills_repo / "policies" / "base.yaml").write_text(
        "default_max_skill_reads: 2\n",
        encoding="utf-8",
    )

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "skill_scheduler.py").write_text("# placeholder", encoding="utf-8")
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

    compile_bundle_for_agents(
        adapters=["codex"],
        bundle_name="engineer",
        skills_repo=skills_repo,
        output_root=output_root,
        project_root=project_root,
        template_root=repo_root / "adapters",
    )

    ir_payload = json.loads((output_root / "codex" / "engineer" / "ir.json").read_text(encoding="utf-8"))
    assert ir_payload["bundle"]["skills"] == ["planning-implementation", "local-station-debug"]
    assert ir_payload["intent_enum"] == ["planning-implementation", "local-station-debug"]
    assert ir_payload["policies"]["max_skill_reads"] == 5
    assert ir_payload["provenance"]["skills"]["local-station-debug"]["layer"] == "bundle.local"
    assert ir_payload["provenance"]["policies"]["max_skill_reads"]["winner"]["layer"] == "bundle.local"


def test_compile_bundle_prefers_local_skill_override(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skills_repo = tmp_path / "my-agent-skills"
    project_root = tmp_path / "target-project"
    output_root = tmp_path / "out"

    _write_skill(
        skills_repo / "planning" / "SKILL.md",
        name="planning-implementation",
        description="Global description",
    )
    (skills_repo / "bundles").mkdir(parents=True, exist_ok=True)
    (skills_repo / "bundles" / "engineer.yaml").write_text(
        "\n".join(
            [
                "name: engineer",
                "skills:",
                "  - planning-implementation",
            ]
        ),
        encoding="utf-8",
    )
    (skills_repo / "policies").mkdir(parents=True, exist_ok=True)
    (skills_repo / "policies" / "base.yaml").write_text(
        "default_max_skill_reads: 3\n",
        encoding="utf-8",
    )

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "skill_scheduler.py").write_text("# placeholder", encoding="utf-8")
    _write_skill(
        project_root / "skills" / "planning" / "SKILL.md",
        name="planning-implementation",
        description="Local override description",
    )

    compile_bundle_for_agents(
        adapters=["codex"],
        bundle_name="engineer",
        skills_repo=skills_repo,
        output_root=output_root,
        project_root=project_root,
        template_root=repo_root / "adapters",
    )

    ir_payload = json.loads((output_root / "codex" / "engineer" / "ir.json").read_text(encoding="utf-8"))
    assert ir_payload["skills"][0]["summary"] == "Local override description"
    assert ir_payload["skills"][0]["path"].endswith("/target-project/skills/planning/SKILL.md")
    assert ir_payload["skills"][0]["source_layer"] == "local"
    assert ir_payload["provenance"]["skill_definitions"]["planning-implementation"]["layer"] == "local"


def test_compile_bundle_tracks_profile_override_provenance(tmp_path: Path) -> None:
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

    compile_bundle_for_agents(
        adapters=["codex"],
        bundle_name="engineer",
        skills_repo=skills_repo,
        output_root=output_root,
        project_root=project_root,
        template_root=repo_root / "adapters",
        max_skill_reads_override=6,
    )

    ir_payload = json.loads((output_root / "codex" / "engineer" / "ir.json").read_text(encoding="utf-8"))
    trace = ir_payload["provenance"]["policies"]["max_skill_reads"]
    assert trace["value"] == 6
    assert trace["winner"]["layer"] == "profile"
    assert [item["layer"] for item in trace["sources"]] == ["bundle", "profile"]


def test_compile_bundle_fails_on_overlay_extends_mismatch(tmp_path: Path) -> None:
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
    (skills_repo / "bundles" / "engineer.yaml").write_text(
        "name: engineer\nskills:\n  - planning-implementation\n",
        encoding="utf-8",
    )
    (skills_repo / "policies").mkdir(parents=True, exist_ok=True)
    (skills_repo / "policies" / "base.yaml").write_text(
        "default_max_skill_reads: 3\n",
        encoding="utf-8",
    )

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "skill_scheduler.py").write_text("# placeholder", encoding="utf-8")
    (project_root / "bundles.local").mkdir(parents=True, exist_ok=True)
    (project_root / "bundles.local" / "engineer.yaml").write_text(
        "extends: finance\nadd_skills:\n  - planning-implementation\n",
        encoding="utf-8",
    )

    try:
        compile_bundle_for_agents(
            adapters=["codex"],
            bundle_name="engineer",
            skills_repo=skills_repo,
            output_root=output_root,
            project_root=project_root,
            template_root=repo_root / "adapters",
        )
    except ValueError as exc:
        assert "extends" in str(exc)
    else:
        raise AssertionError("Expected overlay extends validation error.")
