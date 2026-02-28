#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from services.skill_scheduler import build_default_scheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Schedule skills with a two-stage retrieval flow "
            "(Discover/Filter then Targeted Read)."
        )
    )
    parser.add_argument(
        "--task",
        type=str,
        default="",
        help="Task description used for routing.",
    )
    parser.add_argument(
        "--context",
        type=str,
        default="",
        help="Optional semantic context or intent hint (for example: planning-implementation).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Maximum number of scheduled skills to return.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--max-skill-reads",
        type=int,
        default=3,
        help="Context guardrail for max full skill reads per schedule run.",
    )
    parser.add_argument(
        "--intent-whitelist",
        type=str,
        default="",
        help=(
            "Comma-separated allowed intent values for --context. "
            "When provided, --context must match one of these values."
        ),
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show environment diagnostics without task routing.",
    )
    return parser


def format_text_output(result: dict) -> str:
    if "error" in result:
        err = result["error"]
        return (
            "Scheduler error\n"
            f"- code: {err.get('code', 'unknown')}\n"
            f"- message: {err.get('message', '')}"
        )

    report = result["load_report"]
    config = result.get("config", {})
    diagnostics = result.get("schedule_diagnostics", {})
    lines: list[str] = []

    if result.get("mode") == "status":
        lines.extend(
            [
                "Environment diagnostics",
                f"- git repo: {'yes' if (Path(result.get('repo_root', '.')) / '.git').exists() else 'no'}",
                "",
                "Skill layers",
            ]
        )
        for directory, count in report["scanned_directories"].items():
            lines.append(f"- {directory}: {count} skill(s)")
        if report["missing_directories"]:
            lines.append("- missing directories:")
            for directory in report["missing_directories"]:
                lines.append(f"  - {directory}")

        fallback = result.get("fallback_skills", {})
        if fallback:
            lines.append("")
            lines.append("Fallback skills")
            for skill_id, state in fallback.items():
                lines.append(f"- {skill_id}: {state}")
        return "\n".join(lines)

    lines.extend(
        [
            "Skill preload summary",
            f"- total skills: {report['total_skills']}",
            f"- route hints: {report['route_hints']}",
        ]
    )
    if "max_skill_reads" in config:
        lines.append(f"- max detailed reads: {config['max_skill_reads']}")
    if result.get("context"):
        lines.append(f"- context: {result['context']}")
    if result.get("intent_whitelist"):
        lines.append(
            "- intent whitelist: "
            + ", ".join(result.get("intent_whitelist", []))
        )

    for directory, count in report["scanned_directories"].items():
        lines.append(f"- {directory}: {count} skill file(s)")

    if report["missing_directories"]:
        lines.append("- missing directories:")
        for directory in report["missing_directories"]:
            lines.append(f"  - {directory}")

    if diagnostics:
        lines.append(
            "- detailed reads used: "
            f"{diagnostics.get('detailed_reads_used', 0)}/"
            f"{diagnostics.get('max_detailed_reads', config.get('max_skill_reads', 'n/a'))}"
        )

    decisions = result.get("decisions", [])
    if decisions:
        lines.append("")
        lines.append("Scheduled skills")
        for index, decision in enumerate(decisions, start=1):
            reason_text = "; ".join(decision["reasons"]) if decision["reasons"] else "no reason"
            lines.append(
                f"{index}. {decision['skill_id']} (score={decision['score']}) [{decision['path']}]"
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


def _normalize_intent(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"\s+", "-", lowered)
    lowered = re.sub(r"[^a-z0-9\-]", "", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered


def _parse_intent_whitelist(raw: str) -> list[str]:
    if not raw.strip():
        return []
    values = [_normalize_intent(part) for part in raw.split(",")]
    return [value for value in values if value]


def _build_error(code: str, message: str, result: dict) -> dict:
    payload = dict(result)
    payload["error"] = {"code": code, "message": message}
    return payload


def _run_status_mode(*, repo_root: Path, scheduler, load_report) -> dict:
    fallback_targets = (
        "planning-implementation",
        "planning",
        "managing-environment",
    )
    known_ids = {skill.identifier for skill in scheduler.skills}
    fallback_state = {
        item: ("found" if item in known_ids else "missing")
        for item in fallback_targets
    }
    return {
        "mode": "status",
        "repo_root": str(repo_root),
        "load_report": load_report.to_dict(),
        "fallback_skills": fallback_state,
    }


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

    if args.status:
        status_result = _run_status_mode(
            repo_root=repo_root,
            scheduler=scheduler,
            load_report=load_report,
        )
        if args.format == "json":
            print(json.dumps(status_result, indent=2, ensure_ascii=False))
        else:
            print(format_text_output(status_result))
        return 0

    whitelist = _parse_intent_whitelist(args.intent_whitelist)
    if whitelist:
        normalized_context = _normalize_intent(args.context)
        result["intent_whitelist"] = whitelist
        if not normalized_context:
            payload = _build_error(
                code="invalid_intent",
                message="--context is required when --intent-whitelist is provided.",
                result=result,
            )
            if args.format == "json":
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(format_text_output(payload))
            return 2
        if normalized_context not in whitelist:
            payload = _build_error(
                code="invalid_intent",
                message=(
                    f"context `{args.context}` is not in whitelist: "
                    + ", ".join(whitelist)
                ),
                result=result,
            )
            if args.format == "json":
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(format_text_output(payload))
            return 2

    if args.task.strip():
        query = args.task
        if args.context.strip():
            query = f"{args.task}\n{args.context.strip()}"
            result["context"] = args.context.strip()

        decisions = scheduler.schedule(task_text=query, top_n=max(1, args.top))
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

