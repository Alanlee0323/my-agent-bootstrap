#!/usr/bin/env bash
set -euo pipefail

# Bootstrap Codex routing layer into a target project.
# - Adds/updates my-agent-skills submodule.
# - Copies AGENTS + scheduler files.
# - Runs a health check command.

usage() {
  cat <<'EOF'
Usage:
  tools/bootstrap_agent.sh [options]

Options:
  --target <dir>            Target project directory (default: current directory)
  --source-root <dir>       Source template root (default: parent of this script)
  --skills-url <url>        my-agent-skills git URL
                            (default: https://github.com/Alanlee0323/my-agent-skills.git)
  --skills-path <path>      Submodule path in target repo (default: my-agent-skills)
  --profile <path>          Agent profile yaml path (relative to target or absolute)
  --max-skill-reads <n>     Guardrail value used for health check (default: 3)
  --bundle <name>           Bundle name from my-agent-skills/bundles/<name>.yaml
  --agent <name>            Adapter target: codex|copilot|gemini|all (default: codex)
  --adapter-output <path>   Output directory for compiled adapter artifacts (default: .agent)
  --upgrade                 Re-apply bootstrap using previous state (forces overwrite)
  --update-skills-remote    Update my-agent-skills to latest remote commit
  --clean-stale             Remove stale generated files tracked by previous state
  --force                   Overwrite existing target files
  --skip-submodule          Skip submodule add/update
  --skip-healthcheck        Skip scheduler health check
  --skip-gitnexus           Skip GitNexus analyze step
  --dry-run                 Print actions without applying changes
  -h, --help                Show this help

Examples:
  tools/bootstrap_agent.sh --target /path/to/project
  tools/bootstrap_agent.sh --target . --force
  tools/bootstrap_agent.sh --target . --dry-run
  tools/bootstrap_agent.sh --target . --bundle engineer --agent codex
  tools/bootstrap_agent.sh --target . --profile agent.profile.yaml
  tools/bootstrap_agent.sh --target . --upgrade --update-skills-remote
EOF
}

log() {
  printf '[bootstrap] %s\n' "$*"
}

warn() {
  printf '[bootstrap][warn] %s\n' "$*" >&2
}

die() {
  printf '[bootstrap][error] %s\n' "$*" >&2
  exit 1
}

run() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    printf '+ %q' "$1"
    shift || true
    for arg in "$@"; do
      printf ' %q' "${arg}"
    done
    printf '\n'
    return 0
  fi
  "$@"
}

resolve_target_path() {
  local value="$1"
  if [[ "${value}" == /* ]]; then
    printf '%s\n' "${value}"
    return
  fi
  printf '%s\n' "${TARGET_DIR}/${value}"
}

copy_template_file() {
  local relative_path="$1"
  local src="${SOURCE_ROOT}/${relative_path}"
  local dst="${TARGET_DIR}/${relative_path}"

  [[ -f "${src}" ]] || die "Template file not found: ${src}"

  run mkdir -p "$(dirname "${dst}")"
  if [[ -f "${dst}" && "${FORCE}" != "1" ]]; then
    warn "Skip existing file (use --force to overwrite): ${dst}"
    SKIPPED_FILES+=("${relative_path}")
    return
  fi

  run cp "${src}" "${dst}"
  COPIED_FILES+=("${relative_path}")
}

ensure_git_repo() {
  git -C "${TARGET_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

setup_submodule() {
  if [[ "${SKIP_SUBMODULE}" == "1" ]]; then
    log "Skip submodule setup by request."
    return
  fi

  local skills_abs
  skills_abs="$(resolve_target_path "${SKILLS_PATH}")"
  if ! ensure_git_repo; then
    warn "Target is not a git repo. Falling back to git clone."
    if [[ -d "${skills_abs}" || -f "${skills_abs}/.git" || -f "${skills_abs}" ]]; then
      log "Skills path already exists. Skip clone."
      if [[ "${UPDATE_SKILLS_REMOTE}" == "1" && -d "${skills_abs}/.git" ]]; then
        log "Updating existing skills clone from remote."
        run git -C "${skills_abs}" pull --ff-only || \
          warn "Skills remote pull failed. Please inspect manually."
      fi
      return
    fi
    run git clone "${SKILLS_URL}" "${skills_abs}" || \
      warn "git clone failed. Please inspect manually."
    if [[ "${UPDATE_SKILLS_REMOTE}" == "1" ]]; then
      log "Skills clone already at latest remote after clone."
    fi
    return
  fi

  if [[ -d "${skills_abs}" || -f "${skills_abs}/.git" || -f "${skills_abs}" ]]; then
    log "my-agent-skills path exists. Running submodule update."
  else
    log "Adding my-agent-skills submodule: ${SKILLS_URL} -> ${SKILLS_PATH}"
    run git -C "${TARGET_DIR}" submodule add "${SKILLS_URL}" "${SKILLS_PATH}" || true
  fi

  run git -C "${TARGET_DIR}" submodule update --init --recursive "${SKILLS_PATH}" || \
    warn "Submodule update failed. Please inspect manually."
  if [[ "${UPDATE_SKILLS_REMOTE}" == "1" ]]; then
    log "Updating my-agent-skills submodule to latest remote commit."
    run git -C "${TARGET_DIR}" submodule update --init --remote --recursive "${SKILLS_PATH}" || \
      warn "Submodule remote update failed. Please inspect manually."
  fi
}

setup_gitnexus() {
  if [[ "${SKIP_GITNEXUS}" == "1" ]]; then
    log "Skip GitNexus setup by request."
    return
  fi
  if ! ensure_git_repo; then
    warn "Target is not a git repo. Skip GitNexus analyze."
    return
  fi
  if ! command -v npx >/dev/null 2>&1; then
    warn "npx not found. Skip GitNexus analyze. Install Node.js to enable."
    return
  fi
  log "Running GitNexus analyze on target repo."
  run npx gitnexus analyze "${TARGET_DIR}" || \
    warn "GitNexus analyze failed. Please inspect manually."
}

setup_git_exclude() {
  ensure_git_repo || return
  local exclude_file="${TARGET_DIR}/.git/info/exclude"
  local exclude_dir="${TARGET_DIR}/.git/info"
  [[ -d "${exclude_dir}" ]] || mkdir -p "${exclude_dir}"
  local marker="# Bootstrap agent tools"
  if grep -qF "${marker}" "${exclude_file}" 2>/dev/null; then
    log "Git exclude entries already present. Skip."
    return
  fi
  log "Writing agent paths to .git/info/exclude."
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "+ append to ${exclude_file}"
    return
  fi
  cat >> "${exclude_file}" <<'EXCLUDE'

# Bootstrap agent tools
AGENTS.md
GEMINI.md
CLAUDE.md
skill_scheduler.py
services/skill_scheduler.py
tests/test_skill_scheduler.py
my-agent-skills/
skills/
.gitnexus/
EXCLUDE
}

resolve_python_cmd() {
  if [[ -n "${PYTHON_CMD}" ]]; then
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
    return
  fi
  PYTHON_CMD=""
}

resolve_upgrade_mode_from_state() {
  resolve_python_cmd
  if [[ -z "${PYTHON_CMD}" ]]; then
    die "No python interpreter found; cannot resolve --upgrade mode."
  fi

  local state_tool="${SOURCE_ROOT}/tools/bootstrap_state.py"
  [[ -f "${state_tool}" ]] || die "State helper not found: ${state_tool}"

  local output=""
  if ! output="$("${PYTHON_CMD}" "${state_tool}" resolve --state "${STATE_FILE}" --discover-root "${TARGET_DIR}" 2>/dev/null)"; then
    die "--upgrade requested but no previous bootstrap state found. Provide --profile or --bundle explicitly."
  fi

  while IFS='=' read -r key value; do
    case "${key}" in
      STATE_FILE) STATE_FILE="${value}" ;;
      MODE) ACTIVE_MODE="${value}" ;;
      PROFILE_PATH) PROFILE_PATH="${value}" ;;
      BUNDLE_NAME) BUNDLE_NAME="${value}" ;;
      AGENT_TARGET) AGENT_TARGET="${value}" ;;
      ADAPTER_OUTPUT) ADAPTER_OUTPUT="${value}" ;;
      SKILLS_PATH) SKILLS_PATH="${value}" ;;
      MAX_SKILL_READS) MAX_SKILL_READS="${value}" ;;
      *) ;;
    esac
  done <<< "${output}"

  if [[ -z "${ACTIVE_MODE}" ]]; then
    die "Resolved state is missing mode. Provide --profile or --bundle explicitly."
  fi

  if [[ "${ACTIVE_MODE}" == "profile" && -z "${PROFILE_PATH}" ]]; then
    die "Resolved state mode is profile, but profile path is missing."
  fi
  if [[ "${ACTIVE_MODE}" == "bundle" && -z "${BUNDLE_NAME}" ]]; then
    die "Resolved state mode is bundle, but bundle name is missing."
  fi

  log "Upgrade mode restored from state: mode=${ACTIVE_MODE}, output=${ADAPTER_OUTPUT}"
}

run_health_check() {
  if [[ "${SKIP_HEALTHCHECK}" == "1" ]]; then
    log "Skip health check by request."
    return
  fi

  resolve_python_cmd
  if [[ -z "${PYTHON_CMD}" ]]; then
    warn "No python interpreter found. Skip health check."
    return
  fi

  local scheduler="${TARGET_DIR}/skill_scheduler.py"
  if [[ ! -f "${scheduler}" ]]; then
    warn "Missing scheduler file: ${scheduler}. Skip health check."
    return
  fi

  log "Running scheduler health check."
  run "${PYTHON_CMD}" "${scheduler}" \
    --task "health check" \
    --top 1 \
    --max-skill-reads "${MAX_SKILL_READS}" \
    --format text || warn "Health check failed. Please inspect manually."
}

run_adapter_compile() {
  if [[ -z "${BUNDLE_NAME}" ]]; then
    log "No bundle specified. Skip adapter compile."
    return
  fi

  resolve_python_cmd
  if [[ -z "${PYTHON_CMD}" ]]; then
    die "No python interpreter found; cannot compile adapter artifacts."
  fi

  local compiler="${SOURCE_ROOT}/tools/compile_agent_bundle.py"
  [[ -f "${compiler}" ]] || die "Bundle compiler not found: ${compiler}"

  local skills_repo
  skills_repo="$(resolve_target_path "${SKILLS_PATH}")"
  if [[ ! -d "${skills_repo}" && "${DRY_RUN}" != "1" ]]; then
    die "Skills repo path not found for compile: ${skills_repo}"
  fi
  if [[ ! -d "${skills_repo}" && "${DRY_RUN}" == "1" ]]; then
    warn "Skills repo path not found in dry-run; command will still be printed: ${skills_repo}"
  fi

  local adapter_output_abs
  adapter_output_abs="$(resolve_target_path "${ADAPTER_OUTPUT}")"
  log "Compiling adapter artifacts (agent=${AGENT_TARGET}, bundle=${BUNDLE_NAME})."
  run "${PYTHON_CMD}" "${compiler}" \
    --agent "${AGENT_TARGET}" \
    --bundle "${BUNDLE_NAME}" \
    --skills-repo "${skills_repo}" \
    --output "${adapter_output_abs}" \
    --project-root "${TARGET_DIR}" \
    --max-skill-reads "${MAX_SKILL_READS}" || \
    die "Adapter compile failed."
  COMPILE_EXECUTED="1"
  ACTIVE_MODE="bundle"
}

run_profile_apply() {
  if [[ -z "${PROFILE_PATH}" ]]; then
    return
  fi

  resolve_python_cmd
  if [[ -z "${PYTHON_CMD}" ]]; then
    die "No python interpreter found; cannot apply profile."
  fi

  local applier="${SOURCE_ROOT}/tools/apply_agent_profile.py"
  [[ -f "${applier}" ]] || die "Profile applier not found: ${applier}"

  local profile_abs="${PROFILE_PATH}"
  if [[ "${profile_abs}" != /* ]]; then
    profile_abs="${TARGET_DIR}/${PROFILE_PATH}"
  fi
  if [[ ! -f "${profile_abs}" && "${DRY_RUN}" != "1" ]]; then
    die "Profile file not found: ${profile_abs}"
  fi
  if [[ ! -f "${profile_abs}" && "${DRY_RUN}" == "1" ]]; then
    warn "Profile file not found in dry-run; command will still be printed: ${profile_abs}"
  fi

  local skills_repo
  skills_repo="$(resolve_target_path "${SKILLS_PATH}")"
  log "Applying agent profile: ${profile_abs}"
  run "${PYTHON_CMD}" "${applier}" \
    --profile "${profile_abs}" \
    --project-root "${TARGET_DIR}" \
    --default-skills-repo "${skills_repo}" \
    --template-root "${SOURCE_ROOT}/adapters" || \
    die "Profile apply failed."
  COMPILE_EXECUTED="1"
  ACTIVE_MODE="profile"
}

persist_bootstrap_state() {
  if [[ "${COMPILE_EXECUTED}" != "1" ]]; then
    return
  fi

  resolve_python_cmd
  if [[ -z "${PYTHON_CMD}" ]]; then
    warn "No python interpreter found. Skip bootstrap state update."
    return
  fi

  local state_tool="${SOURCE_ROOT}/tools/bootstrap_state.py"
  if [[ ! -f "${state_tool}" ]]; then
    warn "State helper not found: ${state_tool}. Skip state update."
    return
  fi

  local output_root
  output_root="$(resolve_target_path "${ADAPTER_OUTPUT}")"

  local cmd=(
    "${PYTHON_CMD}" "${state_tool}" reconcile
    --state "${STATE_FILE}"
    --output-root "${output_root}"
    --mode "${ACTIVE_MODE}"
    --project-root "${TARGET_DIR}"
    --adapter-output "${ADAPTER_OUTPUT}"
    --skills-path "${SKILLS_PATH}"
    --max-skill-reads "${MAX_SKILL_READS}"
  )
  if [[ -n "${PROFILE_PATH}" ]]; then
    cmd+=(--profile-path "${PROFILE_PATH}")
  fi
  if [[ -n "${BUNDLE_NAME}" ]]; then
    cmd+=(--bundle-name "${BUNDLE_NAME}")
  fi
  if [[ -n "${AGENT_TARGET}" ]]; then
    cmd+=(--agent-target "${AGENT_TARGET}")
  fi
  if [[ "${CLEAN_STALE}" == "1" ]]; then
    cmd+=(--clean-stale)
  fi

  log "Updating bootstrap state: ${STATE_FILE}"
  run "${cmd[@]}" || warn "Bootstrap state update failed."
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="$(pwd)"
SKILLS_URL="https://github.com/Alanlee0323/my-agent-skills.git"
SKILLS_PATH="my-agent-skills"
PROFILE_PATH=""
MAX_SKILL_READS="3"
AGENT_TARGET="codex"
BUNDLE_NAME=""
ADAPTER_OUTPUT=".agent"
UPGRADE="0"
UPDATE_SKILLS_REMOTE="0"
CLEAN_STALE="0"
FORCE="0"
SKIP_SUBMODULE="0"
SKIP_HEALTHCHECK="0"
DRY_RUN="0"
SKIP_GITNEXUS="0"
PYTHON_CMD=""
ACTIVE_MODE=""
STATE_FILE=""
COMPILE_EXECUTED="0"
COPIED_FILES=()
SKIPPED_FILES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_DIR="${2:-}"
      shift 2
      ;;
    --source-root)
      SOURCE_ROOT="${2:-}"
      shift 2
      ;;
    --skills-url)
      SKILLS_URL="${2:-}"
      shift 2
      ;;
    --skills-path)
      SKILLS_PATH="${2:-}"
      shift 2
      ;;
    --profile)
      PROFILE_PATH="${2:-}"
      shift 2
      ;;
    --max-skill-reads)
      MAX_SKILL_READS="${2:-}"
      shift 2
      ;;
    --bundle)
      BUNDLE_NAME="${2:-}"
      shift 2
      ;;
    --agent)
      AGENT_TARGET="${2:-}"
      shift 2
      ;;
    --adapter-output)
      ADAPTER_OUTPUT="${2:-}"
      shift 2
      ;;
    --upgrade)
      UPGRADE="1"
      shift
      ;;
    --update-skills-remote)
      UPDATE_SKILLS_REMOTE="1"
      shift
      ;;
    --clean-stale)
      CLEAN_STALE="1"
      shift
      ;;
    --force)
      FORCE="1"
      shift
      ;;
    --skip-submodule)
      SKIP_SUBMODULE="1"
      shift
      ;;
    --skip-healthcheck)
      SKIP_HEALTHCHECK="1"
      shift
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    --skip-gitnexus)
      SKIP_GITNEXUS="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

[[ -d "${TARGET_DIR}" ]] || die "Target directory not found: ${TARGET_DIR}"
[[ -d "${SOURCE_ROOT}" ]] || die "Source root not found: ${SOURCE_ROOT}"
if [[ -n "${PROFILE_PATH}" && -n "${BUNDLE_NAME}" ]]; then
  die "Use either --profile or --bundle/--agent options, not both."
fi
if [[ -n "${PROFILE_PATH}" ]]; then
  ACTIVE_MODE="profile"
elif [[ -n "${BUNDLE_NAME}" ]]; then
  ACTIVE_MODE="bundle"
fi

STATE_FILE="$(resolve_target_path "${ADAPTER_OUTPUT}")/bootstrap.state.json"
if [[ "${UPGRADE}" == "1" ]]; then
  FORCE="1"
  if [[ "${CLEAN_STALE}" != "1" ]]; then
    CLEAN_STALE="1"
  fi
  if [[ -z "${ACTIVE_MODE}" ]]; then
    resolve_upgrade_mode_from_state
    if [[ -n "${STATE_FILE}" && "${STATE_FILE}" != /* ]]; then
      STATE_FILE="$(resolve_target_path "${ADAPTER_OUTPUT}")/bootstrap.state.json"
    fi
  fi
fi

[[ "${MAX_SKILL_READS}" =~ ^[0-9]+$ ]] || die "--max-skill-reads must be an integer"
if [[ "${MAX_SKILL_READS}" -lt 1 ]]; then
  MAX_SKILL_READS="1"
fi
case "${AGENT_TARGET}" in
  codex|copilot|gemini|all) ;;
  *) die "--agent must be one of: codex|copilot|gemini|all" ;;
esac
if [[ "${ACTIVE_MODE}" == "profile" && -z "${PROFILE_PATH}" ]]; then
  die "Profile mode requires --profile."
fi
if [[ "${ACTIVE_MODE}" == "bundle" && -z "${BUNDLE_NAME}" ]]; then
  die "Bundle mode requires --bundle."
fi

log "Target: ${TARGET_DIR}"
log "Source root: ${SOURCE_ROOT}"
log "Guardrail max-skill-reads: ${MAX_SKILL_READS}"
if [[ "${UPGRADE}" == "1" ]]; then
  log "Upgrade mode enabled."
fi
if [[ "${UPDATE_SKILLS_REMOTE}" == "1" ]]; then
  log "Skills remote update enabled."
fi
if [[ "${CLEAN_STALE}" == "1" ]]; then
  log "Stale generated file cleanup enabled."
fi
if [[ -n "${PROFILE_PATH}" ]]; then
  log "Profile mode enabled: profile=${PROFILE_PATH}"
fi
if [[ -n "${BUNDLE_NAME}" ]]; then
  log "Bundle compile enabled: bundle=${BUNDLE_NAME}, agent=${AGENT_TARGET}, output=${ADAPTER_OUTPUT}"
fi

setup_submodule

copy_template_file "AGENTS.md"
copy_template_file "GEMINI.md"
copy_template_file "skill_scheduler.py"
copy_template_file "services/skill_scheduler.py"
copy_template_file "tests/test_skill_scheduler.py"
if [[ -n "${PROFILE_PATH}" ]]; then
  run_profile_apply
else
  run_adapter_compile
fi
persist_bootstrap_state

setup_gitnexus
run_health_check
setup_git_exclude

log "Bootstrap complete."
if [[ ${#COPIED_FILES[@]} -gt 0 ]]; then
  log "Copied files:"
  for file in "${COPIED_FILES[@]}"; do
    printf '  - %s\n' "${file}"
  done
fi

if [[ ${#SKIPPED_FILES[@]} -gt 0 ]]; then
  warn "Skipped existing files:"
  for file in "${SKIPPED_FILES[@]}"; do
    printf '  - %s\n' "${file}" >&2
  done
fi
