#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from compiler import SUPPORTED_ADAPTERS, compile_bundle_for_agents


@dataclass(frozen=True)
class AgentProfile:
    name: str
    bundle: str
    agents: list[str]
    skills_repo: str | None
    adapter_output: str
    max_skill_reads: int | None
    generate_launchers: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply an agent profile to compile adapter artifacts for a target project."
    )
    parser.add_argument("--profile", required=True, help="Path to agent.profile.yaml")
    parser.add_argument("--project-root", required=True, help="Target project root path")
    parser.add_argument(
        "--default-skills-repo",
        default="",
        help="Fallback skills repo path when profile does not set skills_repo",
    )
    parser.add_argument(
        "--template-root",
        default=str(REPO_ROOT / "adapters"),
        help="Adapter template root directory",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    profile_path = Path(args.profile).resolve()
    project_root = Path(args.project_root).resolve()
    default_skills_repo = Path(args.default_skills_repo).resolve() if args.default_skills_repo else None
    template_root = Path(args.template_root).resolve()

    if not profile_path.exists():
        print(f"[profile][error] Profile not found: {profile_path}", file=sys.stderr)
        return 1
    if not project_root.exists():
        print(f"[profile][error] Project root not found: {project_root}", file=sys.stderr)
        return 1
    if not template_root.exists():
        print(f"[profile][error] Template root not found: {template_root}", file=sys.stderr)
        return 1

    try:
        profile = load_profile(profile_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[profile][error] Invalid profile: {exc}", file=sys.stderr)
        return 1

    resolved_skills_repo = resolve_profile_path(
        raw=profile.skills_repo,
        base_dir=profile_path.parent,
        fallback=default_skills_repo,
    )
    if resolved_skills_repo is None:
        print(
            "[profile][error] skills_repo missing in profile and no default provided.",
            file=sys.stderr,
        )
        return 1
    if not resolved_skills_repo.exists():
        print(
            f"[profile][error] skills_repo path not found: {resolved_skills_repo}",
            file=sys.stderr,
        )
        return 1

    output_root = resolve_profile_path(
        raw=profile.adapter_output,
        base_dir=project_root,
        fallback=None,
    )
    assert output_root is not None

    try:
        written = compile_bundle_for_agents(
            adapters=profile.agents,
            bundle_name=profile.bundle,
            skills_repo=resolved_skills_repo,
            output_root=output_root,
            project_root=project_root,
            template_root=template_root,
            max_skill_reads_override=profile.max_skill_reads,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[profile][error] Failed to compile profile: {exc}", file=sys.stderr)
        return 1

    launchers: list[Path] = []
    if profile.generate_launchers:
        launchers = write_launchers(
            project_root=project_root,
            output_root=output_root,
            bundle=profile.bundle,
            agents=profile.agents,
        )

    manifest_path = output_root / "profile.manifest.json"
    manifest = {
        "profile_name": profile.name,
        "profile_path": str(profile_path),
        "project_root": str(project_root),
        "skills_repo": str(resolved_skills_repo),
        "bundle": profile.bundle,
        "agents": profile.agents,
        "adapter_output": str(output_root),
        "max_skill_reads": profile.max_skill_reads,
        "generate_launchers": profile.generate_launchers,
        "compiled_files": [str(item) for item in written],
        "launchers": [str(item) for item in launchers],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print("[profile] apply complete")
    print(f"- profile: {profile.name}")
    print(f"- bundle: {profile.bundle}")
    print(f"- agents: {', '.join(profile.agents)}")
    print(f"- skills_repo: {resolved_skills_repo}")
    print(f"- output: {output_root}")
    print(f"- manifest: {manifest_path}")
    return 0


def load_profile(path: Path) -> AgentProfile:
    raw = parse_simple_yaml(path)

    name = str(raw.get("name", path.stem))
    bundle = normalize_identifier(str(raw.get("bundle", "")))
    if not bundle:
        raise ValueError("`bundle` is required.")

    agents = parse_agents(raw)
    if not agents:
        raise ValueError("`agents` (or `agent`) is required.")
    for agent in agents:
        if agent not in SUPPORTED_ADAPTERS:
            raise ValueError(
                f"Unsupported agent `{agent}`. Supported: {', '.join(SUPPORTED_ADAPTERS)}"
            )

    skills_repo = raw.get("skills_repo")
    adapter_output = str(raw.get("adapter_output", ".agent")).strip() or ".agent"

    max_skill_reads = raw.get("max_skill_reads")
    if max_skill_reads is not None:
        if isinstance(max_skill_reads, bool) or not isinstance(max_skill_reads, int):
            raise ValueError("`max_skill_reads` must be an integer.")
        if max_skill_reads < 1:
            raise ValueError("`max_skill_reads` must be >= 1.")

    generate_launchers = bool(raw.get("generate_launchers", True))
    return AgentProfile(
        name=name,
        bundle=bundle,
        agents=agents,
        skills_repo=str(skills_repo).strip() if skills_repo is not None else None,
        adapter_output=adapter_output,
        max_skill_reads=max_skill_reads,
        generate_launchers=generate_launchers,
    )


def parse_agents(raw: dict[str, object]) -> list[str]:
    if "agents" in raw:
        value = raw["agents"]
        if not isinstance(value, list):
            raise ValueError("`agents` must be a YAML list.")
        return [normalize_identifier(str(item)) for item in value if str(item).strip()]

    if "agent" in raw:
        value = normalize_identifier(str(raw["agent"]))
        return [value] if value else []
    return []


def resolve_profile_path(raw: str | None, base_dir: Path, fallback: Path | None) -> Path | None:
    if raw is None:
        return fallback.resolve() if fallback is not None else None

    text = str(raw).strip()
    if not text:
        return fallback.resolve() if fallback is not None else None

    candidate = Path(text)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def parse_simple_yaml(path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    lines = path.read_text(encoding="utf-8").splitlines()

    section = ""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if re.match(r"^\S", line):
            section = ""
            if ":" not in line:
                raise ValueError(f"Invalid YAML line: {line!r}")
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                section = key
                if key == "agents":
                    result[key] = []
                continue
            result[key] = parse_scalar(value)
            continue

        if section == "agents":
            if not stripped.startswith("- "):
                raise ValueError("Invalid agents list item, expected '- value'.")
            item = parse_scalar(stripped[2:])
            casted = result.setdefault("agents", [])
            if isinstance(casted, list):
                casted.append(item)
            continue

    return result


def parse_scalar(value: str) -> object:
    text = value.strip()
    if text.startswith(("'", '"')) and text.endswith(("'", '"')) and len(text) >= 2:
        text = text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def normalize_identifier(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"\s+", "-", lowered)
    lowered = re.sub(r"[^a-z0-9\-]", "", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered


def write_launchers(
    *,
    project_root: Path,
    output_root: Path,
    bundle: str,
    agents: list[str],
) -> list[Path]:
    launcher_dir = output_root / "launchers"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    scheduler_path = (project_root / "skill_scheduler.py").resolve()
    for agent in agents:
        prompt_filename = {
            "codex": "AGENTS.generated.md",
            "copilot": "copilot.prompt.md",
            "gemini": "gemini.prompt.md",
        }[agent]
        prompt_path = (output_root / agent / bundle / prompt_filename).resolve()

        sh_path = launcher_dir / f"launch_{agent}.sh"
        bat_path = launcher_dir / f"launch_{agent}.bat"

        sh_path.write_text(
            build_shell_launcher(
                agent=agent,
                prompt_path=prompt_path,
                scheduler_path=scheduler_path,
                project_root=project_root,
            ),
            encoding="utf-8",
        )
        bat_path.write_text(
            build_bat_launcher(
                agent=agent,
                prompt_path=prompt_path,
                scheduler_path=scheduler_path,
                project_root=project_root,
            ),
            encoding="utf-8",
        )
        written.extend([sh_path, bat_path])

    return written


def build_shell_launcher(
    *,
    agent: str,
    prompt_path: Path,
    scheduler_path: Path,
    project_root: Path,
) -> str:
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            f'export AGENT_BOOTSTRAP_ROOT="{project_root}"',
            f'export AGENT_SCHEDULER_PATH="{scheduler_path}"',
            f'PROMPT_FILE="{prompt_path}"',
            "",
            f'echo "[{agent}] runtime env ready"',
            'echo "AGENT_BOOTSTRAP_ROOT=${AGENT_BOOTSTRAP_ROOT}"',
            'echo "AGENT_SCHEDULER_PATH=${AGENT_SCHEDULER_PATH}"',
            'echo "PROMPT_FILE=${PROMPT_FILE}"',
            "",
            'if [[ $# -eq 0 ]]; then',
            '  echo "Pass your CLI command after this launcher to reuse env context."',
            "  exit 0",
            "fi",
            "",
            '"$@"',
            "",
        ]
    )


def build_bat_launcher(
    *,
    agent: str,
    prompt_path: Path,
    scheduler_path: Path,
    project_root: Path,
) -> str:
    return "\n".join(
        [
            "@echo off",
            "setlocal EnableExtensions",
            f'set "AGENT_BOOTSTRAP_ROOT={project_root}"',
            f'set "AGENT_SCHEDULER_PATH={scheduler_path}"',
            f'set "PROMPT_FILE={prompt_path}"',
            "",
            f'echo [{agent}] runtime env ready',
            "echo AGENT_BOOTSTRAP_ROOT=%AGENT_BOOTSTRAP_ROOT%",
            "echo AGENT_SCHEDULER_PATH=%AGENT_SCHEDULER_PATH%",
            "echo PROMPT_FILE=%PROMPT_FILE%",
            "",
            'if "%~1"=="" (',
            "  echo Pass your CLI command after this launcher to reuse env context.",
            "  exit /b 0",
            ")",
            "",
            "%*",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())

