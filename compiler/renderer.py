from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .models import CompileIR
from .validator import validate_rendered_prompt


ADAPTER_OUTPUT_FILENAMES = {
    "codex": "AGENTS.generated.md",
    "copilot": "copilot.prompt.md",
    "gemini": "gemini.prompt.md",
}


def render_adapter_output(
    *,
    adapter_name: str,
    adapter_template_path: Path,
    ir: CompileIR,
    output_root: Path,
) -> list[Path]:
    if adapter_name not in ADAPTER_OUTPUT_FILENAMES:
        raise ValueError(f"Unsupported adapter: {adapter_name}")

    template = adapter_template_path.read_text(encoding="utf-8")
    skills_bullets = "\n".join(
        f"- `{skill.identifier}`: {skill.description or '(no description)'}"
        for skill in ir.skills
    )
    intent_csv = ", ".join(ir.intent_enum)
    intent_bullets = "\n".join(f"- `{intent}`" for intent in ir.intent_enum)

    rendered = template.format(
        generated_at=datetime.now(timezone.utc).isoformat(),
        bundle_name=ir.bundle.name,
        bundle_description=ir.bundle.description or "(no description)",
        generated_by=ir.generated_by,
        scheduler_command=ir.scheduler_command,
        scheduler_path=ir.scheduler_path,
        bootstrap_root=ir.bootstrap_root,
        intent_csv=intent_csv,
        intent_bullets=intent_bullets,
        skills_bullets=skills_bullets,
        output_language=str(ir.policies.get("output_language", "en")),
        max_skill_reads=int(ir.policies.get("max_skill_reads", 3)),
        max_scheduler_retries=int(ir.policies.get("max_scheduler_retries", 2)),
        retry_on=", ".join(ir.retry_on),
        fail_fast_on=", ".join(ir.fail_fast_on),
    )

    render_errors = validate_rendered_prompt(rendered, ir)
    if render_errors:
        message = "\n".join(f"- {item}" for item in render_errors)
        raise ValueError(f"Rendered prompt validation failed:\n{message}")

    output_dir = output_root / adapter_name / ir.bundle.name
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = output_dir / ADAPTER_OUTPUT_FILENAMES[adapter_name]
    ir_path = output_dir / "ir.json"
    manifest_path = output_dir / "manifest.json"

    prompt_path.write_text(rendered, encoding="utf-8")
    ir_path.write_text(
        json.dumps(ir.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "adapter": adapter_name,
                "bundle": ir.bundle.name,
                "generated_by": ir.generated_by,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "files": [prompt_path.name, ir_path.name],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return [prompt_path, ir_path, manifest_path]

