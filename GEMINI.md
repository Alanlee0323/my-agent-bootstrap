# Commander Policy

This repository uses `my-agent-skills` as the primary skill source. Local `./skills/` is optional and may be empty.

## Mandatory Preload Gate

Before writing code or performing complex tasks, the agent MUST strictly follow this two-stage retrieval flow:

1. `Discover`: Scan directory structures for `./skills/` and `./my-agent-skills/`.
2. `Filter`: Identify available skills by filename, supporting both `SKILL.md` and `skill.md`.
3. `Targeted Read`: Read full content only for skills that are highly relevant to the current task intent. Do not blindly load every skill file.
   - Context Guardrail: default maximum full reads per task is `3` skill files.
4. `Global Constraints`: Read `./my-agent-skills/global-rules.md` when present.
5. `Fault Tolerance`: Continue safely if one directory is missing, and explicitly report which directory is missing in status output.

No implementation work should begin until this preload gate is completed.

## Routing Rules

After preload, select specialized skills based on task intent:

1. Match explicit skill names first.
2. Match "When to use this skill" triggers second.
3. Apply `global-rules.md` routing hints third.
4. If still ambiguous, use planning-oriented defaults first (`planning`, `managing-environment`).

For tasks requiring multiple skills, run them in this order:

1. Intent/plan skill (e.g., `brainstorming`, `planning`)
2. Domain/tool skill (e.g., `using-*`, `cicd-skills`)
3. Safety/review skill (e.g., `handling-review`, `auditing-code`)

## Mandatory Routing Hook (條件式強制閘門)

The agent can judge task complexity, but it MUST run the scheduler command below before execution when any of the following conditions is true:

```bash
python skill_scheduler.py --task "<task description>" --max-skill-reads 3
```

1. Code generation or code modification tasks (new scripts, implementation planning, refactoring, codebase edits).
2. System or environment operations (CI/CD, Docker, deployment, package/dependency management).
3. Multi-step tasks (explicit planning/restructure requests or scope spanning multiple modules).

When any condition above is met, the agent MUST NOT rely only on generic memory and MUST use scheduler output as routing input.

Exception: For pure theory Q&A, syntax explanation, or trivial one-line debugging, the agent may skip the scheduler and answer directly.

## Action Output Format

When switching skills or moving across `Plan -> Domain -> Review`, emit an explicit status line so the workflow is traceable. Example:

`[Routing Status]: Transitioning to <Domain Skill: cicd-skills> for implementation.`

If context guardrail is triggered, also emit a warning that includes skipped/deferred candidate count.

## Conflict Resolution

If rules conflict:

1. Safety and non-destructive behavior first.
2. Project-level `AGENTS.md` rules before skill-local preferences.
3. Ask user clarification only when the conflict cannot be resolved from repository context.
