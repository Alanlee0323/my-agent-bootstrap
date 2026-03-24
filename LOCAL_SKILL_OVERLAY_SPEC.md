# Local Skill Overlay Spec

## 1. Why This Exists

`my-agent-bootstrap` is meant to be reused across many projects, while `my-agent-skills` is a shared skill repository.

In real projects, two things happen at the same time:

1. You want a stable shared base (`my-agent-skills`).
2. Each project will eventually need project-specific skills that should not immediately pollute the shared repository.

This spec defines a flexible mechanism for:

1. Reusing `my-agent-skills` across many projects.
2. Adding project-local skills mid-project.
3. Automatically merging local skills into active bundles.
4. Refreshing Codex / Copilot CLI / Gemini CLI artifacts without manual file surgery.

## 2. Product Goal

The user should be able to:

1. Bootstrap a new project with shared skills.
2. Add a new local skill inside that project.
3. Make that local skill active for the project's bundle without editing shared global bundles by hand.
4. Refresh generated agent artifacts with one command.
5. Update the shared skill package later without losing project-local behavior.

## 3. Non-Goals

This spec does not try to:

1. Replace `Invoke` inside every target project.
2. Force every project to commit the same bootstrap runtime policy.
3. Solve remote skill publishing workflow yet.

`Invoke` remains optional convenience glue at the target-project level. The canonical workflow should live in `my-agent-bootstrap`.

## 4. Plain-Language Model

Think of the system as 3 layers:

1. Global base:
   `my-agent-skills`
   This is the reusable shared skill library.
2. Project local overlay:
   `skills/`, `bundles.local/`, `agent.profile.yaml`
   This is where the project says "for this repo, add these extra rules/skills".
3. Generated runtime:
   `.agent/`, launchers, state files
   These are build artifacts derived from the first 2 layers.

The important rule is:

Project-local behavior should live in the project, not inside the shared `my-agent-skills` submodule.

There is also a fourth concern that must be explicit:

Policy values may come from multiple layers, so the system must explain not just the merged result, but also where each value came from.

## 5. Target Project Filesystem

Recommended target-project layout:

```text
<project>/
  my-agent-skills/                 # shared repo or submodule
  skills/                          # project-local skills
    engineer/
      local-station-debug/
        SKILL.md
  bundles.local/                   # project-local bundle overlays
    engineer.yaml
  agent.profile.yaml               # active project profile
  AGENTS.md
  GEMINI.md
  skill_scheduler.py
  services/skill_scheduler.py
  .agent/                          # generated outputs
```

## 6. Version Control Boundary

### Must Be Version Controlled

These are project source-of-truth:

1. `my-agent-skills/` when used as a submodule or vendored directory.
2. `skills/` project-local skills.
3. `bundles.local/` project-local bundle overlays.
4. `agent.profile.yaml`.
5. Project docs that define workflow expectations.

### Usually Not Version Controlled

These are generated or machine-local:

1. `.agent/`
2. `.gitnexus/`
3. `.git/info/exclude`
4. `bootstrap.state.json`

### Important Clarification

`skills/` must not be ignored.

Reason:

`skills/` is not a cache or build artifact. It is project-specific knowledge and is part of the repo's intended behavior.

## 7. Skill Resolution Rules

### Discovery Order

Scheduler and compiler should support this logical precedence:

1. `./skills/`
2. `./my-agent-skills/`

### Override Behavior

If a local skill and a global skill use the same frontmatter `name`:

1. Local skill wins for that project.
2. This is treated as a project-local override, not a conflict.

If a local skill introduces a new `name`:

1. It becomes available only in that project.

## 8. Bundle Overlay Model

### Base Bundle

Shared bundles still live in:

```text
my-agent-skills/bundles/<bundle>.yaml
```

Example:

```yaml
name: engineer
skills:
  - planning-implementation
  - handling-review
  - managing-environment
```

### Local Overlay

Project-local delta lives in:

```text
bundles.local/<bundle>.yaml
```

Example:

```yaml
extends: engineer
add_skills:
  - local-station-debug
  - local-oqc-troubleshooting
remove_skills: []
policy_overrides:
  max_skill_reads: 4
```

### Merge Algorithm

Given bundle `engineer`, compiler resolves final bundle in this order:

1. Load base bundle from `my-agent-skills/bundles/engineer.yaml`
2. If `bundles.local/engineer.yaml` exists:
   apply overlay
3. Apply `agent.profile.yaml` overrides if present

### Merge Rules

1. `extends` must match the requested base bundle.
2. `add_skills` appends new skills while preserving original base order.
3. `remove_skills` removes matching skills from the base or appended list.
4. Skill ids are deduplicated, keeping first surviving occurrence.
5. `policy_overrides` in local overlay override base policy.
6. Profile-level overrides still win last.

### Policy Precedence

Policy values may be defined in 4 layers:

1. `my-agent-skills/policies/base.yaml`
2. `my-agent-skills/bundles/<bundle>.yaml`
3. `bundles.local/<bundle>.yaml`
4. `agent.profile.yaml`

Last writer wins, but provenance must always be preserved.

### Policy Provenance Requirement

The system must keep a provenance trace for every merged policy field.

Example:

```json
{
  "max_skill_reads": {
    "value": 4,
    "sources": [
      {"layer": "base", "path": "my-agent-skills/policies/base.yaml", "value": 3},
      {"layer": "bundle.local", "path": "bundles.local/engineer.yaml", "value": 4}
    ],
    "winner": {"layer": "bundle.local", "path": "bundles.local/engineer.yaml"}
  }
}
```

This is required so that users can explain unexpected behavior instead of guessing which layer won.

## 9. Canonical Bootstrap Commands

The reusable, cross-project UX should live in `my-agent-bootstrap`, not in per-project `Invoke` tasks.

Recommended canonical commands:

### 9.1 `bootstrap init`

Use when a new project is first connected to `my-agent-bootstrap`.

Responsibilities:

1. Mount or verify `my-agent-skills`
2. Copy runtime bootstrap files
3. Apply `agent.profile.yaml`
4. Generate `.agent/`
5. Persist bootstrap state

### 9.2 `bootstrap refresh`

Use when local skills, local overlays, bundle config, or profile changed.

Responsibilities:

1. Resolve merged bundle
2. Recompile `.agent/`
3. Refresh runtime files if needed
4. Update bootstrap state
5. Clean stale generated artifacts

`bootstrap refresh` should also support:

1. `--dry-run`: show the merged bundle, merged policy tree, and what would be regenerated
2. `--explain`: emit policy provenance and overlay merge details

### 9.3 `bootstrap sync-skills`

Use when the shared `my-agent-skills` repository changed.

Responsibilities:

1. Update submodule or local shared repo
2. Re-run refresh

### 9.4 `bootstrap add-local-skill`

Use when a project needs a new local skill during development.

Responsibilities:

1. Create `skills/<domain>/<skill-name>/SKILL.md`
2. Fill a governed template
3. Optionally append that skill id into `bundles.local/<bundle>.yaml`
4. Optionally trigger refresh

### 9.5 `bootstrap remove-local-skill`

Use when a local skill should stop participating in a project bundle.

Responsibilities:

1. Remove skill id from `bundles.local/<bundle>.yaml`
2. Optionally leave the skill file in place
3. Optionally trigger refresh

### 9.6 `bootstrap doctor`

Use when project state is confusing or after moving between machines.

Responsibilities:

1. Verify submodule state
2. Verify `agent.profile.yaml`
3. Verify `skills/` and `bundles.local/`
4. Verify scheduler and generated outputs
5. Report stale or conflicting state
6. Support `--explain` to show the final merged tree and every policy field's provenance trace

### 9.7 `bootstrap status`

Use when the user wants to know what is currently active.

Responsibilities:

1. Show active profile
2. Show base bundle
3. Show local overlay
4. Show final merged skill list
5. Show generated agents

`bootstrap status` should support:

1. `--json`: machine-readable output
2. `--explain`: full merged bundle tree and policy provenance

### 9.8 `bootstrap build`

Use when the user wants an explicit "preview vs execute" distinction.

Responsibilities:

1. Resolve the same merged inputs as `bootstrap refresh`
2. Show what output files would be written
3. Support `--dry-run` as a first-class preview mode
4. Optionally share implementation with `bootstrap refresh`

At minimum, one of these must exist:

1. `bootstrap refresh --dry-run`
2. `bootstrap build --dry-run`

The product must provide a safe preview mode before writes occur.

## 10. State Consistency and Artifact Freshness

Manual refresh is acceptable as the main execution model, but stale generated artifacts must be detectable.

### Problem

Users will eventually:

1. Edit `skills/`
2. Edit `bundles.local/`
3. Forget to run refresh

This creates a dangerous state where `.agent/` looks valid but no longer matches source-of-truth inputs.

### Required Freshness Signal

The system must persist an input fingerprint in generated state.

Candidate inputs:

1. `skills/`
2. `bundles.local/`
3. `my-agent-skills/bundles/`
4. `my-agent-skills/policies/`
5. `agent.profile.yaml`
6. `my-agent-skills` Git SHA when available

Candidate strategies:

1. content hash of relevant files
2. deterministic manifest hash
3. fallback mtime-based lightweight check when hashing all inputs is too expensive

### Scheduler Startup Guard

`skill_scheduler.py` should perform a lightweight freshness check on startup.

If generated artifacts are stale:

1. warn loudly in text mode
2. emit a machine-readable stale flag in JSON mode
3. optionally recommend the exact recovery command

Example warning:

```text
[bootstrap][warn] Generated agent artifacts are stale. Run: bootstrap refresh
```

Phase 1 may stop at warning-only behavior.

Phase 2 may add optional incremental auto-refresh if it can be made safe and predictable.

## 11. Template Governance

`bootstrap add-local-skill` must not invent ad-hoc templates project by project.

### Canonical Template Source

Default skill templates should live in:

```text
my-agent-bootstrap/templates/
```

Example:

```text
templates/skill/SKILL.md.tmpl
```

### Project-Level Template Override

Projects may optionally define:

```text
.agent-bootstrap.yaml
```

Example responsibilities:

1. override local skill template path
2. define default domain
3. define default bundle target

If no override is present, bootstrap must use its canonical built-in template.

### Governance Rule

Template output should stay structurally consistent across projects even when content differs.

That means the generated skill skeleton should consistently include:

1. frontmatter
2. description
3. `## When to use this skill`
4. basic safety / workflow placeholders where relevant

## 12. Optional Invoke Wrappers

Per-project `Invoke` remains optional convenience glue.

Example wrappers:

1. `inv agents-refresh` -> calls `bootstrap refresh`
2. `inv new-skill` -> calls `bootstrap add-local-skill`
3. `inv agents-check` -> calls `bootstrap doctor`

Rule:

`Invoke` should be a thin wrapper. Business logic should remain in `my-agent-bootstrap`.

## 13. Primary User Flows

### Flow A: New Project

1. Add `my-agent-bootstrap`
2. Add `my-agent-skills` submodule
3. Create `agent.profile.yaml`
4. Run `bootstrap init`

Expected outcome:

1. Runtime files appear
2. `.agent/` is generated
3. Scheduler is ready

### Flow B: Add New Local Skill Mid-Project

1. Run `bootstrap add-local-skill --bundle engineer --skill local-station-debug --domain engineer`
2. Edit the generated `SKILL.md`
3. Run `bootstrap refresh`

Expected outcome:

1. New local skill lives in `skills/`
2. It is added to `bundles.local/engineer.yaml`
3. All generated agent prompts see the updated merged bundle

### Flow C: Update Shared Skills

1. Run `bootstrap sync-skills`

Expected outcome:

1. Shared repo updates
2. Final bundle is recomputed
3. Local overlay remains intact
4. `.agent/` is regenerated

### Flow D: Promote Local Skill To Shared Repository

1. Move skill logic from local `skills/` to global `my-agent-skills`
2. Add skill to shared bundle if it should become reusable
3. Remove skill from `bundles.local/`
4. Run `bootstrap refresh`

Expected outcome:

1. Skill becomes reusable across projects
2. Project no longer needs a local overlay entry for it

## 14. Implementation Scope for Phase 1

Phase 1 should implement only the smallest valuable set:

1. `bundles.local/<bundle>.yaml` overlay support
2. Local-first skill discovery in compiler/runtime resolution
3. `bootstrap refresh`
4. `bootstrap add-local-skill`
5. `bootstrap doctor`
6. provenance-aware `--explain`
7. stale-artifact warning path in scheduler startup
8. canonical templates in `templates/`

This is enough to unlock:

1. Shared global skills
2. Local project skills
3. Safe bundle extension without editing global bundle files

## 15. Validation Rules

Compiler/bootstrap must fail fast when:

1. Overlay `extends` does not match requested bundle.
2. A referenced skill id does not exist after local+global skill indexing.
3. The same local skill id is malformed or missing frontmatter.
4. Overlay introduces unsupported policy keys.
5. A policy provenance trace cannot be constructed for a merged field.
6. A project-level template override points to a missing template.
7. A future multi-overlay or multi-inheritance merge produces unresolved same-priority policy conflicts.
8. A future bundle inheritance graph produces circular dependency.

## 16. Migration Strategy

Existing projects can migrate gradually:

1. Keep current `my-agent-skills` and profile setup
2. Introduce `bundles.local/`
3. Move project-specific skill edits out of shared bundle files
4. Start adding future project-only behavior in `skills/`

No project should be forced to migrate all at once.

## 17. Open Design Questions

1. Should `bootstrap add-local-skill` create empty templates or opinionated templates?
2. Should profile support explicit opt-out of local overlays?
3. Should `bootstrap status` emit text only, or also JSON for wrappers?
4. Should `.github/agents/*` become generated mirrors or thin pointers to `.agent/` outputs?
5. Should the preview surface be `bootstrap refresh --dry-run`, `bootstrap build --dry-run`, or both?
6. Should scheduler staleness detection be hash-first, mtime-first, or adaptive?
7. Should stale state ever auto-refresh, or stay warning-only by default?
8. If bundle inheritance expands beyond `extends`, should conflict policy be warning, error, or explicit resolver config?

## 18. Final Recommendation

The core design decision is:

Do not edit shared bundle files to represent project-only behavior.

Instead:

1. Put project-only skills in `skills/`
2. Put project-only bundle deltas in `bundles.local/`
3. Let `my-agent-bootstrap` merge them automatically during refresh
4. Preserve policy provenance so merged behavior is explainable
5. Detect stale generated artifacts before users debug the wrong thing

That keeps the system reusable, explainable, and safe across many projects.
