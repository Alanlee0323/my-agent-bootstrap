from __future__ import annotations

from .models import BundleSpec, CompileIR


ALLOWED_POLICY_KEYS = {
    "require_scheduler_for_complex_tasks",
    "require_json_output",
    "no_destructive_git",
    "default_max_skill_reads",
    "max_scheduler_retries",
    "require_traceable_routing_status",
    "require_intent_whitelist",
    "require_absolute_scheduler_path",
    "output_language",
    "max_skill_reads",
}


def validate_spec(
    bundle: BundleSpec,
    base_policy: dict[str, object],
    skill_index: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    if not bundle.skills:
        errors.append(f"Bundle `{bundle.name}` has no skills.")

    for skill_id in bundle.skills:
        if skill_id not in skill_index:
            errors.append(f"Bundle `{bundle.name}` references missing skill: {skill_id}")

    for key in base_policy:
        if key not in ALLOWED_POLICY_KEYS:
            errors.append(f"Unknown policy key in base policy: {key}")

    for key in bundle.policy_overrides:
        if key not in ALLOWED_POLICY_KEYS:
            errors.append(f"Unknown policy override key in bundle `{bundle.name}`: {key}")

    return errors


def validate_rendered_prompt(rendered_prompt: str, ir: CompileIR) -> list[str]:
    errors: list[str] = []

    if "Intent Whitelist" not in rendered_prompt:
        errors.append("Rendered prompt is missing Intent Whitelist section.")
    for intent in ir.intent_enum:
        if intent not in rendered_prompt:
            errors.append(f"Rendered prompt is missing whitelisted intent: {intent}")

    if "stdout" not in rendered_prompt.lower() or "stderr" not in rendered_prompt.lower():
        errors.append("Rendered prompt is missing stdout/stderr feedback-loop guidance.")

    scheduler_tokens = [ir.scheduler_path, "AGENT_SCHEDULER_PATH"]
    if not any(token in rendered_prompt for token in scheduler_tokens):
        errors.append("Rendered prompt is missing absolute scheduler path or env fallback.")

    return errors

