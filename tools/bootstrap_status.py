#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from compiler import build_compile_ir
from tools.apply_agent_profile import load_profile, resolve_profile_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect merged bootstrap bundle inputs and explain policy/skill provenance."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--profile", help="Path to agent.profile.yaml")
    source_group.add_argument("--bundle", help="Bundle identifier to inspect")
    parser.add_argument("--skills-repo", help="Path to my-agent-skills repository")
    parser.add_argument(
        "--default-skills-repo",
        default="",
        help="Fallback skills repo path when profile does not set skills_repo",
    )
    parser.add_argument("--project-root", help="Target project root path")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Include merged provenance for skills and policies.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        resolved = resolve_status_inputs(args)
        ir = build_compile_ir(
            bundle_name=resolved["bundle_name"],
            skills_repo=resolved["skills_repo"],
            project_root=resolved["project_root"],
            max_skill_reads_override=resolved["max_skill_reads_override"],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[bootstrap-status][error] {exc}", file=sys.stderr)
        return 1

    payload = format_payload(
        ir=ir,
        skills_repo=resolved["skills_repo"],
        project_root=resolved["project_root"],
        profile_path=resolved["profile_path"],
        explain=args.explain,
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(payload))
    return 0


def resolve_status_inputs(args: argparse.Namespace) -> dict[str, object]:
    if args.profile:
        profile_path = Path(args.profile).resolve()
        if not profile_path.exists():
            raise FileNotFoundError(f"Profile not found: {profile_path}")

        profile = load_profile(profile_path)
        project_root = (
            Path(args.project_root).resolve()
            if args.project_root
            else profile_path.parent.resolve()
        )
        default_skills_repo = (
            Path(args.default_skills_repo).resolve() if args.default_skills_repo else None
        )
        skills_repo = resolve_profile_path(
            raw=profile.skills_repo,
            base_dir=profile_path.parent,
            fallback=default_skills_repo,
        )
        if skills_repo is None:
            raise ValueError("skills_repo missing in profile and no default provided.")
        if not skills_repo.exists():
            raise FileNotFoundError(f"skills_repo path not found: {skills_repo}")
        return {
            "bundle_name": profile.bundle,
            "skills_repo": skills_repo.resolve(),
            "project_root": project_root,
            "max_skill_reads_override": profile.max_skill_reads,
            "profile_path": profile_path,
        }

    if not args.bundle:
        raise ValueError("Either --profile or --bundle is required.")
    if not args.skills_repo:
        raise ValueError("--skills-repo is required when --bundle is used.")
    if not args.project_root:
        raise ValueError("--project-root is required when --bundle is used.")

    skills_repo = Path(args.skills_repo).resolve()
    if not skills_repo.exists():
        raise FileNotFoundError(f"skills_repo path not found: {skills_repo}")
    project_root = Path(args.project_root).resolve()
    if not project_root.exists():
        raise FileNotFoundError(f"Project root not found: {project_root}")
    return {
        "bundle_name": args.bundle,
        "skills_repo": skills_repo,
        "project_root": project_root,
        "max_skill_reads_override": None,
        "profile_path": None,
    }


def format_payload(
    *,
    ir: object,
    skills_repo: Path,
    project_root: Path,
    profile_path: Path | None,
    explain: bool,
) -> dict[str, object]:
    assert hasattr(ir, "to_dict")
    payload = ir.to_dict()  # type: ignore[assignment]
    payload["status"] = {
        "project_root": str(project_root),
        "skills_repo": str(skills_repo),
        "profile_path": str(profile_path) if profile_path is not None else "",
        "explain": explain,
    }
    if not explain:
        return {
            "status": payload["status"],
            "bundle": payload["bundle"],
            "policies": payload["policies"],
            "skills": payload["skills"],
        }
    return payload


def render_text(payload: dict[str, object]) -> str:
    bundle = payload["bundle"]
    status = payload["status"]
    skills = payload.get("skills", [])
    policies = payload.get("policies", {})
    lines = [
        "[bootstrap-status]",
        f"bundle: {bundle['name']}",
        f"project_root: {status['project_root']}",
        f"skills_repo: {status['skills_repo']}",
    ]
    if status.get("profile_path"):
        lines.append(f"profile: {status['profile_path']}")
    lines.append("skills:")
    for item in skills:
        lines.append(
            f"- {item['id']} [definition={item.get('source_layer', 'unknown')}] {item.get('path', '')}"
        )
    lines.append("policies:")
    for key, value in policies.items():
        lines.append(f"- {key} = {value}")

    provenance = payload.get("provenance")
    if isinstance(provenance, dict):
        policy_traces = provenance.get("policies", {})
        if isinstance(policy_traces, dict) and policy_traces:
            lines.append("policy provenance:")
            for key, trace in policy_traces.items():
                winner = trace.get("winner", {})
                lines.append(
                    f"- {key}: winner={winner.get('layer', 'unknown')} path={winner.get('path', '')}"
                )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
