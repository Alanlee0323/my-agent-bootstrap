from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProvenanceEntry:
    layer: str
    path: str
    value: object

    def to_dict(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "path": self.path,
            "value": self.value,
        }


@dataclass(frozen=True)
class PolicyTrace:
    value: object
    sources: list[ProvenanceEntry]
    winner: ProvenanceEntry

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "sources": [item.to_dict() for item in self.sources],
            "winner": self.winner.to_dict(),
        }


@dataclass(frozen=True)
class SkillMeta:
    identifier: str
    description: str
    path: Path
    source_layer: str = "global"


@dataclass(frozen=True)
class BundleSpec:
    name: str
    description: str
    skills: list[str]
    policy_overrides: dict[str, object]
    base_path: Path | None = None
    overlay_path: Path | None = None
    skill_provenance: dict[str, ProvenanceEntry] | None = None
    policy_provenance: dict[str, PolicyTrace] | None = None


@dataclass(frozen=True)
class CompileIR:
    bundle: BundleSpec
    skills: list[SkillMeta]
    policies: dict[str, object]
    intent_enum: list[str]
    scheduler_path: str
    bootstrap_root: str
    scheduler_command: str
    retry_on: list[str]
    fail_fast_on: list[str]
    generated_by: str
    policy_provenance: dict[str, PolicyTrace] | None = None
    skill_definition_provenance: dict[str, ProvenanceEntry] | None = None

    def to_dict(self) -> dict[str, object]:
        bundle_membership = {
            skill_id: entry.to_dict()
            for skill_id, entry in (self.bundle.skill_provenance or {}).items()
        }
        return {
            "bundle": {
                "name": self.bundle.name,
                "description": self.bundle.description,
                "skills": self.bundle.skills,
                "policy_overrides": self.bundle.policy_overrides,
                "base_path": str(self.bundle.base_path) if self.bundle.base_path is not None else "",
                "overlay_path": str(self.bundle.overlay_path) if self.bundle.overlay_path is not None else "",
            },
            "skills": [
                {
                    "id": skill.identifier,
                    "summary": skill.description,
                    "path": str(skill.path),
                    "source_layer": skill.source_layer,
                }
                for skill in self.skills
            ],
            "policies": self.policies,
            "provenance": {
                "skills": bundle_membership,
                "bundle_membership": bundle_membership,
                "skill_definitions": {
                    skill_id: entry.to_dict()
                    for skill_id, entry in (self.skill_definition_provenance or {}).items()
                },
                "policies": {
                    key: trace.to_dict()
                    for key, trace in (self.policy_provenance or {}).items()
                },
            },
            "intent_enum": self.intent_enum,
            "runtime": {
                "scheduler_path": self.scheduler_path,
                "bootstrap_root": self.bootstrap_root,
                "scheduler_env": "AGENT_SCHEDULER_PATH",
                "bootstrap_env": "AGENT_BOOTSTRAP_ROOT",
            },
            "routing_contract": {
                "scheduler_command": self.scheduler_command,
                "execution_order": ["plan", "domain", "review"],
            },
            "retry_policy": {
                "max_retries": int(self.policies.get("max_scheduler_retries", 2)),
                "retry_on": self.retry_on,
                "fail_fast_on": self.fail_fast_on,
            },
            "generated_by": self.generated_by,
        }
