#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from compiler import SUPPORTED_ADAPTERS, compile_bundle_for_agents


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile my-agent-skills bundle into adapter-specific prompt artifacts."
    )
    parser.add_argument(
        "--agent",
        action="append",
        required=True,
        help=f"Target adapter ({', '.join(SUPPORTED_ADAPTERS)}) or `all`. Repeatable.",
    )
    parser.add_argument(
        "--bundle",
        required=True,
        help="Bundle identifier from my-agent-skills/bundles/<bundle>.yaml",
    )
    parser.add_argument(
        "--skills-repo",
        required=True,
        help="Path to my-agent-skills repository.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for compiled adapter artifacts.",
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="Target project root containing skill_scheduler.py.",
    )
    parser.add_argument(
        "--max-skill-reads",
        type=int,
        default=None,
        help="Optional override for bundle max skill reads.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        written = compile_bundle_for_agents(
            adapters=args.agent,
            bundle_name=args.bundle,
            skills_repo=Path(args.skills_repo),
            output_root=Path(args.output),
            project_root=Path(args.project_root),
            max_skill_reads_override=args.max_skill_reads,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[bundle-compiler][error] {exc}", file=sys.stderr)
        return 1

    print("[bundle-compiler] compile complete")
    for path in written:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

