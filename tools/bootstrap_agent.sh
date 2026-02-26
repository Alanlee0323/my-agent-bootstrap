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
  --max-skill-reads <n>     Guardrail value used for health check (default: 3)
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

  local skills_abs="${TARGET_DIR}/${SKILLS_PATH}"
  if ! ensure_git_repo; then
    warn "Target is not a git repo. Falling back to git clone."
    if [[ -d "${skills_abs}" || -f "${skills_abs}/.git" || -f "${skills_abs}" ]]; then
      log "Skills path already exists. Skip clone."
      return
    fi
    run git clone "${SKILLS_URL}" "${skills_abs}" || \
      warn "git clone failed. Please inspect manually."
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="$(pwd)"
SKILLS_URL="https://github.com/Alanlee0323/my-agent-skills.git"
SKILLS_PATH="my-agent-skills"
MAX_SKILL_READS="3"
FORCE="0"
SKIP_SUBMODULE="0"
SKIP_HEALTHCHECK="0"
DRY_RUN="0"
SKIP_GITNEXUS="0"
PYTHON_CMD=""
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
    --max-skill-reads)
      MAX_SKILL_READS="${2:-}"
      shift 2
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
[[ "${MAX_SKILL_READS}" =~ ^[0-9]+$ ]] || die "--max-skill-reads must be an integer"
if [[ "${MAX_SKILL_READS}" -lt 1 ]]; then
  MAX_SKILL_READS="1"
fi

log "Target: ${TARGET_DIR}"
log "Source root: ${SOURCE_ROOT}"
log "Guardrail max-skill-reads: ${MAX_SKILL_READS}"

setup_submodule

copy_template_file "AGENTS.md"
copy_template_file "skill_scheduler.py"
copy_template_file "services/skill_scheduler.py"
copy_template_file "tests/test_skill_scheduler.py"

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
