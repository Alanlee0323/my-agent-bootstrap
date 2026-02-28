from __future__ import annotations

from pathlib import Path
import re

from .models import BundleSpec, SkillMeta


def load_base_policy(skills_repo: Path) -> dict[str, object]:
    policy_path = skills_repo / "policies" / "base.yaml"
    if not policy_path.exists():
        return {}
    raw = _parse_key_value_yaml(policy_path)
    return raw


def load_bundle_spec(skills_repo: Path, bundle_name: str) -> BundleSpec:
    bundle_path = skills_repo / "bundles" / f"{bundle_name}.yaml"
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")

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
    return BundleSpec(
        name=bundle_identifier,
        description=description,
        skills=skills,
        policy_overrides=policy_overrides,
    )


def load_skill_index(skills_repo: Path) -> dict[str, SkillMeta]:
    candidates = sorted(
        path
        for path in skills_repo.rglob("*")
        if path.is_file() and path.name.lower() == "skill.md"
    )

    index: dict[str, SkillMeta] = {}
    for skill_file in candidates:
        frontmatter = _parse_frontmatter(_read_head(skill_file, max_chars=12000))
        identifier = _normalize_id(frontmatter.get("name", "") or skill_file.parent.name)
        description = str(frontmatter.get("description", "")).strip()
        if not identifier:
            continue
        index[identifier] = SkillMeta(
            identifier=identifier,
            description=description,
            path=skill_file,
        )
    return index


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


def _normalize_id(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"\s+", "-", lowered)
    lowered = re.sub(r"[^a-z0-9\-]", "", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered


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

