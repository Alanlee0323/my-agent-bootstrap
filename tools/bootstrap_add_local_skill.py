#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config_utils import normalize_identifier, parse_simple_yaml


@dataclass(frozen=True)
class BootstrapProjectConfig:
    local_skill_template: str | None = None
    default_domain: str | None = None
    default_bundle: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a governed project-local skill skeleton and optionally attach it to bundles.local."
    )
    parser.add_argument("--project-root", required=True, help="Target project root path")
    parser.add_argument("--skill", required=True, help="Skill name or identifier")
    parser.add_argument("--description", required=True, help="Short skill description")
    parser.add_argument("--domain", help="Skill domain; falls back to project config or `shared`")
    parser.add_argument("--bundle", help="Bundle to patch; falls back to project config when present")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        project_root = Path(args.project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")

        config = load_bootstrap_project_config(project_root)
        skill_id = normalize_identifier(args.skill)
        if not skill_id:
            raise ValueError("Skill name must resolve to a non-empty identifier.")

        domain = normalize_identifier(args.domain or config.default_domain or "shared")
        if not domain:
            raise ValueError("Domain must resolve to a non-empty identifier.")

        bundle = normalize_identifier(args.bundle or config.default_bundle or "")
        skill_path = project_root / "skills" / domain / skill_id / "SKILL.md"
        if skill_path.exists():
            raise FileExistsError(f"Local skill already exists: {skill_path}")

        template_path = resolve_skill_template_path(project_root, config)
        rendered = render_skill_template(
            template_path=template_path,
            skill_id=skill_id,
            title=args.skill.strip(),
            domain=domain,
            description=args.description.strip(),
        )
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(rendered, encoding="utf-8")

        overlay_path: Path | None = None
        if bundle:
            overlay_path = upsert_bundle_overlay(
                project_root=project_root,
                bundle_name=bundle,
                skill_id=skill_id,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[bootstrap-add-local-skill][error] {exc}", file=sys.stderr)
        return 1

    print("[bootstrap-add-local-skill] created")
    print(f"- skill: {skill_id}")
    print(f"- path: {skill_path}")
    if overlay_path is not None:
        print(f"- bundle_overlay: {overlay_path}")
    return 0


def load_bootstrap_project_config(project_root: Path) -> BootstrapProjectConfig:
    config_path = project_root / ".agent-bootstrap.yaml"
    if not config_path.exists():
        return BootstrapProjectConfig()
    raw = parse_simple_yaml(config_path)
    template = raw.get("local_skill_template")
    default_domain = raw.get("default_domain")
    default_bundle = raw.get("default_bundle")
    return BootstrapProjectConfig(
        local_skill_template=str(template).strip() if template is not None else None,
        default_domain=str(default_domain).strip() if default_domain is not None else None,
        default_bundle=str(default_bundle).strip() if default_bundle is not None else None,
    )


def resolve_skill_template_path(project_root: Path, config: BootstrapProjectConfig) -> Path:
    if config.local_skill_template:
        candidate = Path(config.local_skill_template)
        template_path = (
            candidate.resolve()
            if candidate.is_absolute()
            else (project_root / candidate).resolve()
        )
    else:
        template_path = (REPO_ROOT / "templates" / "skill" / "SKILL.md.tmpl").resolve()
    if not template_path.exists():
        raise FileNotFoundError(f"Skill template not found: {template_path}")
    return template_path


def render_skill_template(
    *,
    template_path: Path,
    skill_id: str,
    title: str,
    domain: str,
    description: str,
) -> str:
    template = template_path.read_text(encoding="utf-8")
    replacements = {
        "{{skill_id}}": skill_id,
        "{{title}}": title.strip() or skill_id,
        "{{domain}}": domain,
        "{{description}}": description,
        "{{description_lower}}": description[:1].lower() + description[1:] if description else "",
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered.rstrip() + "\n"


def upsert_bundle_overlay(*, project_root: Path, bundle_name: str, skill_id: str) -> Path:
    overlay_path = project_root / "bundles.local" / f"{bundle_name}.yaml"
    overlay = load_bundle_overlay_file(overlay_path)
    extends = normalize_identifier(str(overlay.get("extends", "") or bundle_name))
    add_skills = [normalize_identifier(str(item)) for item in overlay.get("add_skills", [])]
    remove_skills = [normalize_identifier(str(item)) for item in overlay.get("remove_skills", [])]
    policy_overrides = {
        str(key): value for key, value in overlay.get("policy_overrides", {}).items()
    }

    if skill_id not in add_skills:
        add_skills.append(skill_id)
    remove_skills = [item for item in remove_skills if item != skill_id]

    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.write_text(
        serialize_bundle_overlay(
            extends=extends or bundle_name,
            add_skills=add_skills,
            remove_skills=remove_skills,
            policy_overrides=policy_overrides,
        ),
        encoding="utf-8",
    )
    return overlay_path


def load_bundle_overlay_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "extends": "",
            "add_skills": [],
            "remove_skills": [],
            "policy_overrides": {},
        }

    extends = ""
    add_skills: list[str] = []
    remove_skills: list[str] = []
    policy_overrides: dict[str, object] = {}
    section = ""

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if not raw_line.startswith((" ", "\t")):
            section = ""
            key, value = split_key_value(raw_line)
            if key == "extends":
                extends = str(value)
            elif key == "add_skills":
                section = "add_skills"
            elif key == "remove_skills":
                section = "remove_skills"
            elif key == "policy_overrides":
                section = "policy_overrides"
            continue

        if section in {"add_skills", "remove_skills"} and line.startswith("- "):
            item = normalize_identifier(line[2:].strip())
            if not item:
                continue
            if section == "add_skills":
                add_skills.append(item)
            else:
                remove_skills.append(item)
            continue

        if section == "policy_overrides":
            key, value = split_key_value(line)
            policy_overrides[key] = parse_scalar(value)

    return {
        "extends": extends,
        "add_skills": add_skills,
        "remove_skills": remove_skills,
        "policy_overrides": policy_overrides,
    }


def serialize_bundle_overlay(
    *,
    extends: str,
    add_skills: list[str],
    remove_skills: list[str],
    policy_overrides: dict[str, object],
) -> str:
    lines = [f"extends: {normalize_identifier(extends)}", "add_skills:"]
    for skill_id in add_skills:
        lines.append(f"  - {normalize_identifier(skill_id)}")
    if remove_skills:
        lines.append("remove_skills:")
        for skill_id in remove_skills:
            lines.append(f"  - {normalize_identifier(skill_id)}")
    if policy_overrides:
        lines.append("policy_overrides:")
        for key, value in policy_overrides.items():
            lines.append(f"  {key}: {value}")
    return "\n".join(lines) + "\n"


def split_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"Invalid YAML key/value line: {line!r}")
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def parse_scalar(value: str) -> object:
    parsed = value.strip()
    if parsed.startswith(("'", '"')) and parsed.endswith(("'", '"')) and len(parsed) >= 2:
        return parsed[1:-1]
    lowered = parsed.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if parsed.lstrip("-").isdigit():
        return int(parsed)
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
