from __future__ import annotations

from pathlib import Path
import re

from config_utils import normalize_identifier
from .models import BundleSpec, PolicyTrace, ProvenanceEntry, SkillMeta


def load_base_policy(skills_repo: Path) -> dict[str, object]:
    policy_path = skills_repo / "policies" / "base.yaml"
    if not policy_path.exists():
        return {}
    raw = _parse_key_value_yaml(policy_path)
    return raw


def load_bundle_spec(skills_repo: Path, bundle_name: str, project_root: Path | None = None) -> BundleSpec:
    normalized_bundle_name = normalize_identifier(bundle_name)
    bundle_path = skills_repo / "bundles" / f"{normalized_bundle_name}.yaml"
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")
    base_bundle = _parse_bundle_file(bundle_path, normalized_bundle_name)
    if project_root is None:
        return base_bundle

    overlay = _load_bundle_overlay(project_root, normalized_bundle_name)
    if overlay is None:
        return base_bundle

    expected_bundle = normalize_identifier(base_bundle.name or normalized_bundle_name)
    overlay_extends = normalize_identifier(str(overlay.get("extends", "")))
    if overlay_extends and overlay_extends != expected_bundle:
        raise ValueError(
            f"Local overlay for `{normalized_bundle_name}` has invalid extends `{overlay_extends}`; expected `{expected_bundle}`."
        )

    merged_skills = _merge_skill_lists(
        base_bundle.skills,
        overlay.get("add_skills", []),
        overlay.get("remove_skills", []),
    )
    merged_skill_provenance = dict(base_bundle.skill_provenance or {})
    for skill_id in overlay.get("add_skills", []):
        normalized = str(skill_id)
        if normalized not in merged_skill_provenance:
            merged_skill_provenance[normalized] = ProvenanceEntry(
                layer="bundle.local",
                path=str(overlay["path"]),
                value=normalized,
            )
    for skill_id in overlay.get("remove_skills", []):
        merged_skill_provenance.pop(str(skill_id), None)

    merged_policy_overrides = dict(base_bundle.policy_overrides)
    merged_policy_overrides.update(overlay.get("policy_overrides", {}))
    merged_policy_provenance = dict(base_bundle.policy_provenance or {})
    for key, value in overlay.get("policy_overrides", {}).items():
        entry = ProvenanceEntry(
            layer="bundle.local",
            path=str(overlay["path"]),
            value=value,
        )
        previous = merged_policy_provenance.get(key)
        if previous is None:
            merged_policy_provenance[key] = PolicyTrace(
                value=value,
                sources=[entry],
                winner=entry,
            )
        else:
            merged_policy_provenance[key] = PolicyTrace(
                value=value,
                sources=[*previous.sources, entry],
                winner=entry,
            )
    return BundleSpec(
        name=base_bundle.name,
        description=base_bundle.description,
        skills=merged_skills,
        policy_overrides=merged_policy_overrides,
        base_path=base_bundle.base_path,
        overlay_path=Path(str(overlay["path"])),
        skill_provenance=merged_skill_provenance,
        policy_provenance=merged_policy_provenance,
    )


def load_skill_index(skills_repo: Path, project_root: Path | None = None) -> dict[str, SkillMeta]:
    index: dict[str, SkillMeta] = {}
    for skill_file in _find_skill_files(skills_repo):
        _register_skill(index, skill_file, source_layer="global")
    if project_root is not None:
        local_skills_root = project_root / "skills"
        if local_skills_root.exists() and local_skills_root.is_dir():
            for skill_file in _find_skill_files(local_skills_root):
                _register_skill(index, skill_file, source_layer="local")
    return index


def _parse_bundle_file(bundle_path: Path, bundle_name: str) -> BundleSpec:
    name = ""
    description = ""
    skills: list[str] = []
    policy_overrides: dict[str, object] = {}
    section = ""

    for line in bundle_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if re.match(r"^\S", line):
            section = ""
            key, value = _split_key_value(line)
            if key == "name":
                name = str(_parse_scalar(value))
            elif key == "description":
                description = str(_parse_scalar(value))
            elif key == "skills":
                section = "skills"
            elif key == "policy_overrides":
                section = "policy_overrides"
            continue

        if section == "skills":
            stripped = line.strip()
            if stripped.startswith("- "):
                skills.append(str(_parse_scalar(stripped[2:])))
            continue

        if section == "policy_overrides":
            key, value = _split_key_value(line.strip())
            policy_overrides[key] = _parse_scalar(value)

    bundle_identifier = name or bundle_name
    skill_provenance = {
        skill_id: ProvenanceEntry(layer="bundle", path=str(bundle_path), value=skill_id)
        for skill_id in skills
    }
    policy_provenance = {
        key: PolicyTrace(
            value=value,
            sources=[ProvenanceEntry(layer="bundle", path=str(bundle_path), value=value)],
            winner=ProvenanceEntry(layer="bundle", path=str(bundle_path), value=value),
        )
        for key, value in policy_overrides.items()
    }
    return BundleSpec(
        name=bundle_identifier,
        description=description,
        skills=skills,
        policy_overrides=policy_overrides,
        base_path=bundle_path,
        overlay_path=None,
        skill_provenance=skill_provenance,
        policy_provenance=policy_provenance,
    )


def _load_bundle_overlay(project_root: Path, bundle_name: str) -> dict[str, object] | None:
    overlay_path = project_root / "bundles.local" / f"{bundle_name}.yaml"
    if not overlay_path.exists():
        return None

    extends = ""
    add_skills: list[str] = []
    remove_skills: list[str] = []
    policy_overrides: dict[str, object] = {}
    section = ""

    for line in overlay_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^\S", line):
            section = ""
            key, value = _split_key_value(line)
            if key == "extends":
                extends = str(_parse_scalar(value))
            elif key == "add_skills":
                section = "add_skills"
            elif key == "remove_skills":
                section = "remove_skills"
            elif key == "policy_overrides":
                section = "policy_overrides"
            continue

        if section in {"add_skills", "remove_skills"}:
            if stripped.startswith("- "):
                item = str(_parse_scalar(stripped[2:]))
                if section == "add_skills":
                    add_skills.append(item)
                else:
                    remove_skills.append(item)
            continue

        if section == "policy_overrides":
            key, value = _split_key_value(stripped)
            policy_overrides[key] = _parse_scalar(value)

    return {
        "extends": extends,
        "add_skills": add_skills,
        "remove_skills": remove_skills,
        "policy_overrides": policy_overrides,
        "path": overlay_path,
    }


def _merge_skill_lists(
    base_skills: list[str],
    add_skills: object,
    remove_skills: object,
) -> list[str]:
    merged = [str(item) for item in base_skills]
    additions = [str(item) for item in add_skills] if isinstance(add_skills, list) else []
    removals = {str(item) for item in remove_skills} if isinstance(remove_skills, list) else set()

    for skill_id in additions:
        if skill_id not in merged:
            merged.append(skill_id)
    return [skill_id for skill_id in merged if skill_id not in removals]


def _find_skill_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name.lower() == "skill.md"
    )


def _register_skill(index: dict[str, SkillMeta], skill_file: Path, *, source_layer: str) -> None:
    frontmatter = _parse_frontmatter(_read_head(skill_file, max_chars=12000))
    identifier = normalize_identifier(frontmatter.get("name", "") or skill_file.parent.name)
    description = str(frontmatter.get("description", "")).strip()
    if not identifier:
        return
    index[identifier] = SkillMeta(
        identifier=identifier,
        description=description,
        path=skill_file,
        source_layer=source_layer,
    )


def _parse_key_value_yaml(path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = _split_key_value(stripped)
        result[key] = _parse_scalar(value)
    return result


def _split_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"Invalid YAML key/value line: {line!r}")
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def _parse_scalar(raw: str) -> object:
    text = raw.strip()
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

def _read_head(path: Path, max_chars: int) -> str:
    with path.open("r", encoding="utf-8") as handle:
        return handle.read(max_chars)


def _parse_frontmatter(content: str) -> dict[str, str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}

    frontmatter: dict[str, str] = {}
    for raw in lines[1:end_index]:
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip("'\"")
    return frontmatter
