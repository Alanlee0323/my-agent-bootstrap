#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.skill_scheduler import build_default_scheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "先建立技能索引（Discover/Filter），再針對候選技能做目標讀取（Targeted Read）並提供排程建議。"
        )
    )
    parser.add_argument(
        "--task",
        type=str,
        default="",
        help="要路由的任務描述。若留空，只輸出技能載入摘要。",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="最多回傳幾個技能建議。",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="輸出格式。",
    )
    parser.add_argument(
        "--max-skill-reads",
        type=int,
        default=3,
        help="每次排程最多允許全文讀取幾個技能檔（Context Guardrail）。",
    )
    return parser


def format_text_output(result: dict) -> str:
    report = result["load_report"]
    config = result.get("config", {})
    diagnostics = result.get("schedule_diagnostics", {})
    lines: list[str] = [
        "Skill preload summary",
        f"- total skills: {report['total_skills']}",
        f"- route hints: {report['route_hints']}",
    ]
    if "max_skill_reads" in config:
        lines.append(f"- max detailed reads: {config['max_skill_reads']}")

    for directory, count in report["scanned_directories"].items():
        lines.append(f"- {directory}: {count} skill file(s)")

    if report["missing_directories"]:
        lines.append("- missing directories:")
        for directory in report["missing_directories"]:
            lines.append(f"  - {directory}")

    if diagnostics:
        lines.append("- detailed reads used: "
                     f"{diagnostics.get('detailed_reads_used', 0)}/"
                     f"{diagnostics.get('max_detailed_reads', config.get('max_skill_reads', 'n/a'))}")

    decisions = result.get("decisions", [])
    if decisions:
        lines.append("")
        lines.append("Scheduled skills")
        for index, decision in enumerate(decisions, start=1):
            reason_text = "; ".join(decision["reasons"]) if decision["reasons"] else "no reason"
            lines.append(
                f"{index}. {decision['skill_id']} "
                f"(score={decision['score']}) [{decision['path']}]"
            )
            lines.append(f"   reason: {reason_text}")

    if diagnostics.get("guardrail_triggered"):
        lines.append("")
        lines.append("Warnings")
        lines.append(
            "- context guardrail triggered: "
            f"skipped/deferred {diagnostics.get('skipped_due_to_limit_total', 0)} "
            "candidate(s) due to max detailed read limit"
        )
        lines.append(
            "- phase summary: "
            f"ranked={diagnostics.get('initial_ranked_candidates', 0)}, "
            f"initial_skipped={diagnostics.get('initial_unread_due_to_limit', 0)}, "
            f"second_pass_skipped={diagnostics.get('second_pass_unread_due_to_limit', 0)}"
        )
        sample_skipped = diagnostics.get("sample_skipped_skill_ids") or []
        if sample_skipped:
            lines.append(f"- sample skipped skills: {', '.join(sample_skipped)}")

    return "\n".join(lines)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    scheduler = build_default_scheduler(
        repo_root=repo_root,
        max_detailed_reads=max(1, args.max_skill_reads),
    )
    load_report = scheduler.load()

    result: dict = {
        "load_report": load_report.to_dict(),
        "config": {"max_skill_reads": max(1, args.max_skill_reads)},
    }
    if args.task.strip():
        decisions = scheduler.schedule(task_text=args.task, top_n=max(1, args.top))
        result["task"] = args.task
        result["decisions"] = [decision.to_dict() for decision in decisions]
        result["schedule_diagnostics"] = scheduler.get_last_schedule_diagnostics()

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_text_output(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
