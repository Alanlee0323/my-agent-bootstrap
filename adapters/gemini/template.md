# Gemini CLI Adapter Prompt

generated_at={generated_at}
generated_by={generated_by}
bundle={bundle_name}
bundle_description={bundle_description}

## Runtime Contract

- Project root: `{bootstrap_root}`
- Scheduler path: `{scheduler_path}`
- Preferred language: `{output_language}`
- Max skill reads: `{max_skill_reads}`

Execute scheduler before implementation or environment operations.

Scheduler command template:
`{scheduler_command}`

Path contract:
- Use `AGENT_SCHEDULER_PATH` when available; otherwise use the absolute scheduler path above.
- Never assume current working directory for scheduler execution.

## Intent Whitelist

Allowed `<intent>` values:
{intent_bullets}

Rules:
- Strictly use only these intents.
- Reject out-of-list intents and request bundle/intention clarification.

## Feedback Loop

After every scheduler run:
1. Parse `stdout` and `stderr`.
2. For retryable errors (`{retry_on}`), update context and retry up to `{max_scheduler_retries}` times.
3. For fatal errors (`{fail_fast_on}`), stop and report.
4. On success, provide routing summary before continuing.

## Available Skills

{skills_bullets}

