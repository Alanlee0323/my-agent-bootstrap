from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def compute_input_fingerprint(
    *,
    project_root: Path,
    skills_repo: Path | None = None,
    profile_path: Path | None = None,
) -> dict[str, object]:
    resolved_project_root = project_root.resolve()
    resolved_skills_repo = skills_repo.resolve() if skills_repo is not None else None
    resolved_profile_path = profile_path.resolve() if profile_path is not None else None

    entries: list[dict[str, object]] = []
    entries.extend(_snapshot_tree(resolved_project_root / "skills", label="project.skills"))
    entries.extend(
        _snapshot_tree(
            resolved_project_root / "bundles.local",
            label="project.bundles.local",
        )
    )
    entries.extend(_snapshot_file(resolved_profile_path, label="project.profile"))
    if resolved_skills_repo is not None:
        entries.extend(_snapshot_shared_repo(resolved_skills_repo))

    skills_repo_git_sha = _read_git_head_sha(resolved_skills_repo) if resolved_skills_repo else ""
    payload = {
        "version": 1,
        "algorithm": "sha256-stat-v1",
        "project_root": str(resolved_project_root),
        "skills_repo": str(resolved_skills_repo) if resolved_skills_repo is not None else "",
        "profile_path": str(resolved_profile_path) if resolved_profile_path is not None else "",
        "skills_repo_git_sha": skills_repo_git_sha,
        "entries": entries,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    payload["digest"] = digest
    return payload


def detect_artifact_freshness(project_root: Path) -> dict[str, object]:
    resolved_project_root = project_root.resolve()
    output_root, manifest_path, manifest_kind = _discover_manifest(resolved_project_root)
    if manifest_path is None or manifest_kind is None:
        return {
            "available": False,
            "is_stale": False,
            "manifest_kind": "",
            "manifest_path": "",
            "output_root": str(output_root) if output_root is not None else "",
            "reason": "bootstrap manifest not found",
            "recovery_command": "tools/bootstrap_agent.sh --target . --upgrade",
        }

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored = payload.get("input_fingerprint")
    if not isinstance(stored, dict):
        return {
            "available": True,
            "is_stale": True,
            "manifest_kind": manifest_kind,
            "manifest_path": str(manifest_path),
            "output_root": str(output_root),
            "reason": "manifest missing input_fingerprint",
            "recovery_command": "tools/bootstrap_agent.sh --target . --upgrade",
        }

    skills_repo = _resolve_manifest_path(
        raw=payload.get("skills_repo") or payload.get("skills_path"),
        project_root=resolved_project_root,
    )
    profile_path = _resolve_manifest_path(
        raw=payload.get("profile_path"),
        project_root=resolved_project_root,
    )
    current = compute_input_fingerprint(
        project_root=resolved_project_root,
        skills_repo=skills_repo,
        profile_path=profile_path,
    )
    stored_digest = str(stored.get("digest", "")).strip()
    current_digest = str(current.get("digest", "")).strip()
    is_stale = stored_digest != current_digest
    return {
        "available": True,
        "is_stale": is_stale,
        "manifest_kind": manifest_kind,
        "manifest_path": str(manifest_path),
        "output_root": str(output_root),
        "stored_digest": stored_digest,
        "current_digest": current_digest,
        "skills_repo_git_sha": current.get("skills_repo_git_sha", ""),
        "reason": "input fingerprint changed" if is_stale else "",
        "recovery_command": "tools/bootstrap_agent.sh --target . --upgrade",
    }


def _snapshot_tree(root: Path, *, label: str) -> list[dict[str, object]]:
    if not root.exists() or not root.is_dir():
        return [{"label": label, "path": str(root), "exists": False, "type": "tree"}]

    entries: list[dict[str, object]] = []
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        entries.append({"label": label, "path": str(root), "exists": True, "type": "tree-empty"})
        return entries

    for path in files:
        stat = path.stat()
        entries.append(
            {
                "label": label,
                "path": path.relative_to(root).as_posix(),
                "exists": True,
                "type": "file",
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return entries


def _snapshot_file(path: Path | None, *, label: str) -> list[dict[str, object]]:
    if path is None:
        return [{"label": label, "path": "", "exists": False, "type": "file"}]
    if not path.exists() or not path.is_file():
        return [{"label": label, "path": str(path), "exists": False, "type": "file"}]
    stat = path.stat()
    return [
        {
            "label": label,
            "path": str(path),
            "exists": True,
            "type": "file",
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    ]


def _snapshot_shared_repo(skills_repo: Path) -> list[dict[str, object]]:
    if not skills_repo.exists() or not skills_repo.is_dir():
        return [{"label": "shared.repo", "path": str(skills_repo), "exists": False, "type": "tree"}]

    selected: list[Path] = []
    for path in skills_repo.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(skills_repo)
        if path.name.lower() == "skill.md":
            selected.append(path)
            continue
        if rel.parts and rel.parts[0] in {"bundles", "policies"}:
            selected.append(path)
            continue
        if rel.as_posix() == "global-rules.md":
            selected.append(path)

    if not selected:
        return [{"label": "shared.repo", "path": str(skills_repo), "exists": True, "type": "tree-empty"}]

    entries: list[dict[str, object]] = []
    for path in sorted(selected):
        stat = path.stat()
        entries.append(
            {
                "label": "shared.repo",
                "path": path.relative_to(skills_repo).as_posix(),
                "exists": True,
                "type": "file",
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return entries


def _discover_manifest(project_root: Path) -> tuple[Path | None, Path | None, str | None]:
    default_output_root = project_root / ".agent"
    profile_manifest = default_output_root / "profile.manifest.json"
    if profile_manifest.exists():
        return default_output_root, profile_manifest, "profile"
    bundle_manifest = default_output_root / "bundle.manifest.json"
    if bundle_manifest.exists():
        return default_output_root, bundle_manifest, "bundle"

    state_path = _discover_state_path(project_root)
    if state_path is None:
        return None, None, None
    output_root = state_path.parent
    profile_manifest = output_root / "profile.manifest.json"
    if profile_manifest.exists():
        return output_root, profile_manifest, "profile"
    bundle_manifest = output_root / "bundle.manifest.json"
    if bundle_manifest.exists():
        return output_root, bundle_manifest, "bundle"
    return output_root, None, None


def _discover_state_path(project_root: Path) -> Path | None:
    default_state = project_root / ".agent" / "bootstrap.state.json"
    if default_state.exists():
        return default_state
    matches = sorted(project_root.rglob("bootstrap.state.json"))
    if len(matches) == 1:
        return matches[0]
    return None


def _resolve_manifest_path(raw: object, *, project_root: Path) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate.resolve()
    return (project_root / candidate).resolve()


def _read_git_head_sha(skills_repo: Path | None) -> str:
    if skills_repo is None:
        return ""
    git_marker = skills_repo / ".git"
    git_dir = _resolve_git_dir(git_marker, skills_repo)
    if git_dir is None:
        return ""

    head_path = git_dir / "HEAD"
    if not head_path.exists():
        return ""
    head = head_path.read_text(encoding="utf-8").strip()
    if head.startswith("ref: "):
        ref_name = head[5:].strip()
        ref_path = git_dir / ref_name
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8").strip()
        packed_refs = git_dir / "packed-refs"
        if packed_refs.exists():
            for line in packed_refs.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("^"):
                    continue
                sha, _, ref = stripped.partition(" ")
                if ref == ref_name:
                    return sha.strip()
        return ""
    return head


def _resolve_git_dir(git_marker: Path, repo_root: Path) -> Path | None:
    if git_marker.is_dir():
        return git_marker
    if not git_marker.exists() or not git_marker.is_file():
        return None
    content = git_marker.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    if not content.lower().startswith(prefix):
        return None
    raw_git_dir = content[len(prefix) :].strip()
    candidate = Path(raw_git_dir)
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()
