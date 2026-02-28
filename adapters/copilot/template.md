# Copilot CLI Adapter Prompt

generated_at={generated_at}
generated_by={generated_by}
bundle={bundle_name}
bundle_description={bundle_description}

## Runtime Contract

- Project root: `{bootstrap_root}`
- Scheduler path: `{scheduler_path}`
- Preferred language: `{output_language}`
- Max skill reads: `{max_skill_reads}`

Before code edits or multi-step tasks, execute scheduler first.

Scheduler command template:
`{scheduler_command}`

Path contract:
- Resolve scheduler from `AGENT_SCHEDULER_PATH` or absolute path above.
- Avoid relative-path execution for `skill_scheduler.py`.

## Intent Whitelist

Allowed `<intent>` values:
{intent_bullets}

Rules:
- `<intent>` must be selected from this enum only.
- If task does not map to allowed intents, stop and ask for clarification.

## Feedback Loop

After scheduler command:
1. Inspect `stdout` and `stderr`.
2. Retry only for `{retry_on}`, with max `{max_scheduler_retries}` retries.
3. Fail immediately for `{fail_fast_on}`.
4. If successful, summarize routing result and proceed.

## Available Skills

{skills_bullets}

