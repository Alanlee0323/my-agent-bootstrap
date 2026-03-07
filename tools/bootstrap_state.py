#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ADAPTERS = ("codex", "copilot", "gemini")
ADAPTER_FILES = (
    "AGENTS.generated.md",
    "copilot.prompt.md",
    "gemini.prompt.md",
    "ir.json",
    "manifest.json",
)
TOP_LEVEL_FILES = ("profile.manifest.json", "bundle.manifest.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve and persist bootstrap state for repeatable upgrade runs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve", help="Resolve bootstrap mode from existing state.")
    resolve.add_argument(
        "--state",
        default="",
        help="Path to bootstrap.state.json. Optional when --discover-root is provided.",
    )
    resolve.add_argument(
        "--discover-root",
        default="",
        help="Optional root path to auto-discover bootstrap.state.json when --state is missing.",
    )

    reconcile = subparsers.add_parser(
        "reconcile",
        help="Update bootstrap state and optionally clean stale generated artifacts.",
    )
    reconcile.add_argument("--state", required=True, help="Path to bootstrap.state.json")
    reconcile.add_argument("--output-root", required=True, help="Adapter output root")
    reconcile.add_argument(
        "--mode",
        required=True,
        choices=("profile", "bundle"),
        help="Compilation mode used in this run.",
    )
    reconcile.add_argument("--project-root", default="", help="Target project root path")
    reconcile.add_argument("--profile-path", default="", help="Profile path for profile mode")
    reconcile.add_argument("--bundle-name", default="", help="Bundle name for bundle mode")
    reconcile.add_argument("--agent-target", default="", help="Agent target for bundle mode")
    reconcile.add_argument("--adapter-output", default="", help="Adapter output directory text")
    reconcile.add_argument("--skills-path", default="", help="Skills path in target project")
    reconcile.add_argument(
        "--max-skill-reads",
        type=int,
        default=None,
        help="Configured max skill reads for this run.",
    )
    reconcile.add_argument(
        "--clean-stale",
        action="store_true",
        help="Remove stale files tracked in previous bootstrap state.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "resolve":
        return command_resolve(args)
    if args.command == "reconcile":
        return command_reconcile(args)
    parser.error("Unknown command.")
    return 1


def command_resolve(args: argparse.Namespace) -> int:
    try:
        state_path = _resolve_state_path(args.state, args.discover_root)
        payload = _load_state(state_path)
    except FileNotFoundError as exc:
        print(f"[bootstrap][state][error] {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"[bootstrap][state][error] {exc}", file=sys.stderr)
        return 1

    _emit_env("STATE_FILE", str(state_path))
    _emit_env("MODE", str(payload.get("mode", "")).strip())
    _emit_env("PROFILE_PATH", str(payload.get("profile_path", "")).strip())
    _emit_env("BUNDLE_NAME", str(payload.get("bundle_name", "")).strip())
    _emit_env("AGENT_TARGET", str(payload.get("agent_target", "")).strip())
    _emit_env("ADAPTER_OUTPUT", str(payload.get("adapter_output", "")).strip())
    _emit_env("SKILLS_PATH", str(payload.get("skills_path", "")).strip())
    max_reads = payload.get("max_skill_reads")
    if isinstance(max_reads, int):
        _emit_env("MAX_SKILL_READS", str(max_reads))
    return 0


def command_reconcile(args: argparse.Namespace) -> int:
    state_path = Path(args.state).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    previous_payload: dict[str, object] = {}
    previous_generated: set[str] = set()
    if state_path.exists():
        try:
            previous_payload = _load_state(state_path)
            previous_generated = {
                item
                for item in previous_payload.get("generated_files", [])
                if isinstance(item, str) and item.strip()
            }
        except Exception as exc:  # noqa: BLE001
            print(
                f"[bootstrap][state][warn] Ignore invalid previous state: {exc}",
                file=sys.stderr,
            )

    bundle_manifest = output_root / "bundle.manifest.json"
    if args.mode == "bundle":
        bundle_payload = {
            "mode": "bundle",
            "bundle": args.bundle_name.strip(),
            "agent": args.agent_target.strip(),
            "adapter_output": args.adapter_output.strip(),
            "skills_path": args.skills_path.strip(),
            "max_skill_reads": args.max_skill_reads,
            "generated_at": _now_iso(),
            "generated_files": [],
        }
        bundle_manifest.write_text(
            json.dumps(bundle_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    current_generated = _collect_generated_files(output_root)

    if args.mode == "bundle":
        bundle_payload = {
            "mode": "bundle",
            "bundle": args.bundle_name.strip(),
            "agent": args.agent_target.strip(),
            "adapter_output": args.adapter_output.strip(),
            "skills_path": args.skills_path.strip(),
            "max_skill_reads": args.max_skill_reads,
            "generated_at": _now_iso(),
            "generated_files": sorted(current_generated),
        }
        bundle_manifest.write_text(
            json.dumps(bundle_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        current_generated = _collect_generated_files(output_root)

    stale_removed: list[str] = []
    if args.clean_stale and previous_generated:
        stale_candidates = sorted(previous_generated - current_generated)
        for rel_path in stale_candidates:
            if not _is_managed_relative_path(rel_path):
                continue
            stale_path = output_root / rel_path
            if not stale_path.exists() or not stale_path.is_file():
                continue
            stale_path.unlink()
            stale_removed.append(rel_path)
            _remove_empty_parents(stale_path.parent, stop_dir=output_root)

    profile_path = args.profile_path.strip()
    bundle_name = args.bundle_name.strip()
    agent_target = args.agent_target.strip()
    adapter_output = args.adapter_output.strip()
    skills_path = args.skills_path.strip()
    project_root = args.project_root.strip()

    state_payload = {
        "version": 1,
        "updated_at": _now_iso(),
        "mode": args.mode,
        "profile_path": profile_path or previous_payload.get("profile_path", ""),
        "bundle_name": bundle_name or previous_payload.get("bundle_name", ""),
        "agent_target": agent_target or previous_payload.get("agent_target", ""),
        "adapter_output": adapter_output or previous_payload.get("adapter_output", ""),
        "skills_path": skills_path or previous_payload.get("skills_path", ""),
        "project_root": project_root or previous_payload.get("project_root", ""),
        "max_skill_reads": (
            args.max_skill_reads
            if args.max_skill_reads is not None
            else previous_payload.get("max_skill_reads", None)
        ),
        "generated_files": sorted(current_generated),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"[bootstrap][state] mode={args.mode}")
    print(f"[bootstrap][state] generated_files={len(current_generated)}")
    print(f"[bootstrap][state] stale_removed={len(stale_removed)}")
    print(f"[bootstrap][state] state_file={state_path}")
    return 0


def _resolve_state_path(state: str, discover_root: str) -> Path:
    if state:
        direct = Path(state).resolve()
        if direct.exists():
            return direct

    if discover_root:
        root = Path(discover_root).resolve()
        if root.exists():
            matches = sorted(root.rglob("bootstrap.state.json"))
            if len(matches) == 1:
                return matches[0].resolve()
            if len(matches) > 1:
                joined = ", ".join(str(item) for item in matches)
                raise ValueError(f"Multiple bootstrap.state.json files found: {joined}")

    if state:
        raise FileNotFoundError(f"State file not found: {Path(state).resolve()}")
    raise FileNotFoundError("State file not found.")


def _load_state(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("State payload must be an object.")
    return payload


def _emit_env(key: str, value: str) -> None:
    if value:
        print(f"{key}={value}")


def _collect_generated_files(output_root: Path) -> set[str]:
    result: set[str] = set()

    for adapter in ADAPTERS:
        adapter_dir = output_root / adapter
        if not adapter_dir.exists() or not adapter_dir.is_dir():
            continue
        for bundle_dir in adapter_dir.iterdir():
            if not bundle_dir.is_dir():
                continue
            for filename in ADAPTER_FILES:
                candidate = bundle_dir / filename
                if candidate.exists() and candidate.is_file():
                    result.add(candidate.relative_to(output_root).as_posix())

    for filename in TOP_LEVEL_FILES:
        candidate = output_root / filename
        if candidate.exists() and candidate.is_file():
            result.add(candidate.relative_to(output_root).as_posix())

    launcher_dir = output_root / "launchers"
    if launcher_dir.exists() and launcher_dir.is_dir():
        for launcher in launcher_dir.iterdir():
            if (
                launcher.is_file()
                and launcher.name.startswith("launch_")
                and launcher.suffix in (".bat", ".sh")
            ):
                result.add(launcher.relative_to(output_root).as_posix())

    return result


def _is_managed_relative_path(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").strip("/")
    if not normalized:
        return False

    if normalized in TOP_LEVEL_FILES:
        return True

    if normalized.startswith("launchers/"):
        name = normalized.split("/", 1)[1]
        return name.startswith("launch_") and (name.endswith(".bat") or name.endswith(".sh"))

    parts = normalized.split("/")
    if len(parts) != 3:
        return False
    adapter, _, filename = parts
    if adapter not in ADAPTERS:
        return False
    return filename in ADAPTER_FILES


def _remove_empty_parents(path: Path, *, stop_dir: Path) -> None:
    current = path
    stop_dir = stop_dir.resolve()
    while True:
        try:
            current.resolve().relative_to(stop_dir)
        except ValueError:
            return

        if current == stop_dir:
            return
        if current.exists() and current.is_dir():
            try:
                current.rmdir()
            except OSError:
                return
        current = current.parent


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
