from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillMeta:
    identifier: str
    description: str
    path: Path


@dataclass(frozen=True)
class BundleSpec:
    name: str
    description: str
    skills: list[str]
    policy_overrides: dict[str, object]


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

    def to_dict(self) -> dict[str, object]:
        return {
            "bundle": {
                "name": self.bundle.name,
                "description": self.bundle.description,
                "skills": self.bundle.skills,
                "policy_overrides": self.bundle.policy_overrides,
            },
            "skills": [
                {
                    "id": skill.identifier,
                    "summary": skill.description,
                    "path": str(skill.path),
                }
                for skill in self.skills
            ],
            "policies": self.policies,
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

