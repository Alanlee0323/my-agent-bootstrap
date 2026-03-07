from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_resolve_state_from_discover_root(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    project_root = tmp_path / "project"
    state_path = project_root / ".agent" / "bootstrap.state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "mode": "bundle",
                "bundle_name": "engineer",
                "agent_target": "codex",
                "adapter_output": ".agent",
                "skills_path": "my-agent-skills",
                "max_skill_reads": 4,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "bootstrap_state.py"),
            "resolve",
            "--discover-root",
            str(project_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    assert "MODE=bundle" in output
    assert "BUNDLE_NAME=engineer" in output
    assert "AGENT_TARGET=codex" in output
    assert "MAX_SKILL_READS=4" in output


def test_reconcile_cleans_stale_files_and_writes_state(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output_root = tmp_path / ".agent"
    state_path = output_root / "bootstrap.state.json"

    stale_file = output_root / "codex" / "old-bundle" / "AGENTS.generated.md"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text("old", encoding="utf-8")

    keep_file = output_root / "codex" / "engineer" / "AGENTS.generated.md"
    keep_file.parent.mkdir(parents=True, exist_ok=True)
    keep_file.write_text("new", encoding="utf-8")
    (output_root / "codex" / "engineer" / "ir.json").write_text("{}", encoding="utf-8")
    (output_root / "codex" / "engineer" / "manifest.json").write_text("{}", encoding="utf-8")

    state_path.write_text(
        json.dumps(
            {
                "mode": "bundle",
                "generated_files": [
                    "codex/old-bundle/AGENTS.generated.md",
                    "codex/engineer/AGENTS.generated.md",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "bootstrap_state.py"),
            "reconcile",
            "--state",
            str(state_path),
            "--output-root",
            str(output_root),
            "--mode",
            "bundle",
            "--bundle-name",
            "engineer",
            "--agent-target",
            "codex",
            "--adapter-output",
            ".agent",
            "--skills-path",
            "my-agent-skills",
            "--max-skill-reads",
            "3",
            "--clean-stale",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not stale_file.exists()
    assert keep_file.exists()
    assert (output_root / "bundle.manifest.json").exists()

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "bundle"
    assert "codex/engineer/AGENTS.generated.md" in payload["generated_files"]
