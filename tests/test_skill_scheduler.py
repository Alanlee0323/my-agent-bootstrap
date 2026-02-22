import os
import sys
from pathlib import Path


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.skill_scheduler import SkillScheduler


def write_skill_file(path: Path, name: str, description: str, triggers: list[str]) -> None:
    trigger_lines = "\n".join([f"- {trigger}" for trigger in triggers])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                "",
                "## When to use this skill",
                trigger_lines,
                "",
                "## Workflow",
                "- Placeholder",
            ]
        ),
        encoding="utf-8",
    )


def test_loads_skill_files_from_both_directories(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    my_agent_skills_dir = tmp_path / "my-agent-skills"

    write_skill_file(
        skills_dir / "planning" / "SKILL.md",
        name="planning-implementation",
        description="Planning helper",
        triggers=["when user asks implementation plan"],
    )
    write_skill_file(
        my_agent_skills_dir / "review" / "skill.md",
        name="handling-review",
        description="Review helper",
        triggers=["when user asks to address review feedback"],
    )
    (my_agent_skills_dir / "global-rules.md").write_text(
        "- **Feedback/Requests** → `handling-review`\n",
        encoding="utf-8",
    )

    scheduler = SkillScheduler(
        skill_directories=[skills_dir, my_agent_skills_dir],
        global_rule_files=[my_agent_skills_dir / "global-rules.md"],
    )
    report = scheduler.load()

    assert report.total_skills == 2
    assert report.scanned_directories[str(skills_dir)] == 1
    assert report.scanned_directories[str(my_agent_skills_dir)] == 1
    assert report.route_hints == 1
    assert report.missing_directories == []
    assert all(not skill.details_loaded for skill in scheduler.skills)


def test_schedule_matches_trigger_and_global_rule(tmp_path: Path):
    my_agent_skills_dir = tmp_path / "my-agent-skills"
    write_skill_file(
        my_agent_skills_dir / "cicd" / "SKILL.md",
        name="managing-cicd-workflow",
        description="Deploy and pipeline workflow helper",
        triggers=["deploy to production", "pipeline failed"],
    )
    (my_agent_skills_dir / "global-rules.md").write_text(
        "- **Deployment** → `cicd-skills`\n",
        encoding="utf-8",
    )

    scheduler = SkillScheduler(
        skill_directories=[tmp_path / "skills", my_agent_skills_dir],
        global_rule_files=[my_agent_skills_dir / "global-rules.md"],
    )
    scheduler.load()

    decisions = scheduler.schedule("Can you help me deploy to production now?", top_n=3)

    assert len(decisions) >= 1
    assert decisions[0].skill.identifier == "managing-cicd-workflow"
    assert any("trigger match" in reason for reason in decisions[0].reasons)


def test_schedule_uses_fallback_for_ambiguous_task(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    write_skill_file(
        skills_dir / "planning" / "SKILL.md",
        name="planning-implementation",
        description="Planning helper",
        triggers=["how to implement"],
    )
    write_skill_file(
        skills_dir / "environment" / "SKILL.md",
        name="managing-environment",
        description="Environment helper",
        triggers=["install packages"],
    )

    scheduler = SkillScheduler(
        skill_directories=[skills_dir, tmp_path / "my-agent-skills"],
        global_rule_files=[],
    )
    scheduler.load()

    decisions = scheduler.schedule("random text without known keywords", top_n=5)

    assert len(decisions) == 2
    assert decisions[0].skill.identifier == "planning-implementation"
    assert decisions[1].skill.identifier == "managing-environment"
    assert decisions[0].reasons == ["fallback default for ambiguous task"]


def test_schedule_matches_chinese_trigger(tmp_path: Path):
    my_agent_skills_dir = tmp_path / "my-agent-skills"
    write_skill_file(
        my_agent_skills_dir / "cicd" / "SKILL.md",
        name="managing-cicd-workflow",
        description="Deploy helper",
        triggers=["部署到正式環境", "pipeline failed"],
    )

    scheduler = SkillScheduler(
        skill_directories=[tmp_path / "skills", my_agent_skills_dir],
        global_rule_files=[],
    )
    scheduler.load()

    decisions = scheduler.schedule("請協助部署到正式環境", top_n=3)

    assert len(decisions) >= 1
    assert decisions[0].skill.identifier == "managing-cicd-workflow"
    assert any("trigger match" in reason for reason in decisions[0].reasons)


def test_schedule_respects_max_detailed_reads_limit(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    for idx in range(4):
        write_skill_file(
            skills_dir / f"deploy-skill-{idx}" / "SKILL.md",
            name=f"deploy-skill-{idx}",
            description="Deploy helper for production release",
            triggers=[f"deploy flow trigger {idx}"],
        )

    scheduler = SkillScheduler(
        skill_directories=[skills_dir, tmp_path / "my-agent-skills"],
        global_rule_files=[],
        max_detailed_reads=2,
    )
    scheduler.load()

    decisions = scheduler.schedule("Please deploy to production", top_n=5)
    diagnostics = scheduler.get_last_schedule_diagnostics()

    assert len(decisions) == 4
    loaded_count = sum(1 for skill in scheduler.skills if skill.details_loaded)
    assert loaded_count == 2
    assert diagnostics["guardrail_triggered"] is True
    assert diagnostics["skipped_due_to_limit_total"] >= 1
    assert diagnostics["detailed_reads_used"] == 2
