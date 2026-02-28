# Codex Adapter Prompt

generated_at={generated_at}
generated_by={generated_by}
bundle={bundle_name}
bundle_description={bundle_description}

## Runtime Contract

- Project root: `{bootstrap_root}`
- Scheduler path: `{scheduler_path}`
- Preferred language: `{output_language}`
- Max skill reads: `{max_skill_reads}`

Always run scheduler for complex tasks before implementation.

Scheduler command template:
`{scheduler_command}`

Fallback path contract:
- Prefer `AGENT_SCHEDULER_PATH`; if unset, use the absolute scheduler path above.
- Do not execute `python skill_scheduler.py` with unresolved relative paths.

## Intent Whitelist

Allowed `<intent>` values:
{intent_bullets}

Blocked behavior:
- Do not invent or infer intents outside this list.
- If no allowed intent fits, request clarification or bundle change.

## Feedback Loop

After every scheduler execution:
1. Read and parse `stdout` and `stderr`.
2. If command fails with retryable type (`{retry_on}`), refine `<context>` and retry up to `{max_scheduler_retries}` times.
3. Fail fast for (`{fail_fast_on}`).
4. On success, summarize selected skills, confidence, and next action.

## Available Skills

{skills_bullets}

