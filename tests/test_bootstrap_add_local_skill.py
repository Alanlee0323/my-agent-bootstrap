from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_add_local_skill_uses_canonical_template_and_creates_overlay(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    project_root = tmp_path / "target-project"
    project_root.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "bootstrap_add_local_skill.py"),
            "--project-root",
            str(project_root),
            "--skill",
            "Local Station Debug",
            "--description",
            "Project-only station debugging workflow",
            "--domain",
            "Engineer",
            "--bundle",
            "Engineer",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    skill_path = project_root / "skills" / "engineer" / "local-station-debug" / "SKILL.md"
    overlay_path = project_root / "bundles.local" / "engineer.yaml"
    assert skill_path.exists()
    assert overlay_path.exists()

    skill_text = skill_path.read_text(encoding="utf-8")
    assert "name: local-station-debug" in skill_text
    assert "description: Project-only station debugging workflow" in skill_text
    assert "## When to use this skill" in skill_text
    assert "## Guardrails" in skill_text

    overlay_text = overlay_path.read_text(encoding="utf-8")
    assert "extends: engineer" in overlay_text
    assert "  - local-station-debug" in overlay_text


def test_add_local_skill_uses_project_override_defaults(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    project_root = tmp_path / "target-project"
    project_root.mkdir(parents=True, exist_ok=True)
    template_path = project_root / "custom-skill-template.md.tmpl"
    template_path.write_text(
        "\n".join(
            [
                "---",
                "name: {{skill_id}}",
                "description: {{description}}",
                "domain: {{domain}}",
                "---",
                "",
                "# {{title}}",
                "custom-template=true",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / ".agent-bootstrap.yaml").write_text(
        "\n".join(
            [
                f"local_skill_template: {template_path.name}",
                "default_domain: engineer",
                "default_bundle: engineer",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "bootstrap_add_local_skill.py"),
            "--project-root",
            str(project_root),
            "--skill",
            "Probe Capture",
            "--description",
            "Capture station probe diagnostics",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    skill_path = project_root / "skills" / "engineer" / "probe-capture" / "SKILL.md"
    overlay_path = project_root / "bundles.local" / "engineer.yaml"
    assert skill_path.exists()
    assert overlay_path.exists()

    skill_text = skill_path.read_text(encoding="utf-8")
    assert "# Probe Capture" in skill_text
    assert "custom-template=true" in skill_text
    assert "domain: engineer" in skill_text


def test_add_local_skill_fails_when_override_template_is_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    project_root = tmp_path / "target-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".agent-bootstrap.yaml").write_text(
        "\n".join(
            [
                "local_skill_template: missing-template.md.tmpl",
                "default_domain: engineer",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "bootstrap_add_local_skill.py"),
            "--project-root",
            str(project_root),
            "--skill",
            "Probe Capture",
            "--description",
            "Capture station probe diagnostics",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "template" in completed.stderr.lower()
