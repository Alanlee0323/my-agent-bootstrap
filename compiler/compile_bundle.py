from __future__ import annotations

from pathlib import Path

from .models import CompileIR, PolicyTrace, ProvenanceEntry, SkillMeta
from .renderer import render_adapter_output
from .spec_loader import load_base_policy, load_bundle_spec, load_skill_index
from .validator import validate_spec


SUPPORTED_ADAPTERS = ("codex", "copilot", "gemini")
RETRY_ON = ["parse_error", "no_match"]
FAIL_FAST_ON = ["missing_scheduler", "invalid_intent"]
PROJECT_ROOT_TOKEN = "<project-root>"
SCHEDULER_PATH_TOKEN = "skill_scheduler.py"
RESOLVED_SCHEDULER_TOKEN = "<resolved-scheduler-path>"


def compile_bundle_for_agents(
    *,
    adapters: list[str],
    bundle_name: str,
    skills_repo: Path,
    output_root: Path,
    project_root: Path,
    template_root: Path | None = None,
    max_skill_reads_override: int | None = None,
) -> list[Path]:
    normalized_adapters = _normalize_adapters(adapters)
    output_root = output_root.resolve()
    resolved_template_root = (
        template_root.resolve()
        if template_root is not None
        else (Path(__file__).resolve().parent.parent / "adapters")
    )
    ir = build_compile_ir(
        bundle_name=bundle_name,
        skills_repo=skills_repo,
        project_root=project_root,
        max_skill_reads_override=max_skill_reads_override,
    )

    written_files: list[Path] = []
    for adapter in normalized_adapters:
        template_path = resolved_template_root / adapter / "template.md"
        if not template_path.exists():
            raise FileNotFoundError(f"Adapter template missing: {template_path}")
        written_files.extend(
            render_adapter_output(
                adapter_name=adapter,
                adapter_template_path=template_path,
                ir=ir,
                output_root=output_root,
            )
        )

    return written_files


def build_compile_ir(
    *,
    bundle_name: str,
    skills_repo: Path,
    project_root: Path,
    max_skill_reads_override: int | None = None,
) -> CompileIR:
    skills_repo = skills_repo.resolve()
    project_root = project_root.resolve()

    base_policy = load_base_policy(skills_repo)
    bundle = load_bundle_spec(skills_repo, bundle_name, project_root=project_root)
    skill_index = load_skill_index(skills_repo, project_root=project_root)

    spec_errors = validate_spec(bundle, base_policy, skill_index)
    if spec_errors:
        joined = "\n".join(f"- {item}" for item in spec_errors)
        raise ValueError(f"Spec validation failed:\n{joined}")

    selected_skills: list[SkillMeta] = [skill_index[item] for item in bundle.skills]
    merged_policies = dict(base_policy)
    policy_provenance = _build_base_policy_provenance(base_policy, skills_repo)
    for key, trace in (bundle.policy_provenance or {}).items():
        merged_policies[key] = trace.value
        previous = policy_provenance.get(key)
        if previous is None:
            policy_provenance[key] = trace
        else:
            policy_provenance[key] = PolicyTrace(
                value=trace.value,
                sources=[*previous.sources, *trace.sources],
                winner=trace.winner,
            )
    if max_skill_reads_override is not None:
        merged_policies["max_skill_reads"] = max(1, int(max_skill_reads_override))
        entry = ProvenanceEntry(
            layer="profile",
            path=str(project_root / "agent.profile.yaml"),
            value=merged_policies["max_skill_reads"],
        )
        previous = policy_provenance.get("max_skill_reads")
        if previous is None:
            policy_provenance["max_skill_reads"] = PolicyTrace(
                value=merged_policies["max_skill_reads"],
                sources=[entry],
                winner=entry,
            )
        else:
            policy_provenance["max_skill_reads"] = PolicyTrace(
                value=merged_policies["max_skill_reads"],
                sources=[*previous.sources, entry],
                winner=entry,
            )
    elif "max_skill_reads" not in merged_policies:
        merged_policies["max_skill_reads"] = int(
            merged_policies.get("default_max_skill_reads", 3)
        )
        entry = ProvenanceEntry(
            layer="derived",
            path="compiler.compile_bundle",
            value=merged_policies["max_skill_reads"],
        )
        policy_provenance["max_skill_reads"] = PolicyTrace(
            value=merged_policies["max_skill_reads"],
            sources=[entry],
            winner=entry,
        )

    scheduler_path = SCHEDULER_PATH_TOKEN
    scheduler_command = (
        f'python "{RESOLVED_SCHEDULER_TOKEN}" --task "<task>" --context "<intent>" '
        f'--max-skill-reads {int(merged_policies["max_skill_reads"])} '
        f'--intent-whitelist "{",".join(bundle.skills)}" --format json'
    )
    skill_definition_provenance = {
        skill.identifier: ProvenanceEntry(
            layer=skill.source_layer,
            path=str(skill.path),
            value=skill.description,
        )
        for skill in selected_skills
    }
    return CompileIR(
        bundle=bundle,
        skills=selected_skills,
        policies=merged_policies,
        intent_enum=bundle.skills,
        scheduler_path=scheduler_path,
        bootstrap_root=PROJECT_ROOT_TOKEN,
        scheduler_command=scheduler_command,
        retry_on=RETRY_ON,
        fail_fast_on=FAIL_FAST_ON,
        generated_by="agent-bootstrap-bundle-compiler@1.0.0",
        policy_provenance=policy_provenance,
        skill_definition_provenance=skill_definition_provenance,
    )


def _build_base_policy_provenance(
    base_policy: dict[str, object],
    skills_repo: Path,
) -> dict[str, PolicyTrace]:
    policy_path = skills_repo / "policies" / "base.yaml"
    result: dict[str, PolicyTrace] = {}
    for key, value in base_policy.items():
        entry = ProvenanceEntry(
            layer="base",
            path=str(policy_path),
            value=value,
        )
        result[key] = PolicyTrace(
            value=value,
            sources=[entry],
            winner=entry,
        )
    return result


def _normalize_adapters(adapters: list[str]) -> list[str]:
    normalized: list[str] = []
    for adapter in adapters:
        lowered = adapter.strip().lower()
        if lowered == "all":
            normalized.extend(SUPPORTED_ADAPTERS)
            continue
        if lowered not in SUPPORTED_ADAPTERS:
            raise ValueError(
                f"Unsupported adapter `{adapter}`. Supported values: {', '.join(SUPPORTED_ADAPTERS)}, all"
            )
        normalized.append(lowered)

    deduped: list[str] = []
    for item in normalized:
        if item not in deduped:
            deduped.append(item)
    if not deduped:
        raise ValueError("No adapters provided.")
    return deduped
