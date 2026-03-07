@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "SOURCE_ROOT=%%~fI"
set "TARGET_DIR=%CD%"
set "SKILLS_URL=https://github.com/Alanlee0323/my-agent-skills.git"
set "SKILLS_PATH=my-agent-skills"
set "PROFILE_PATH="
set "MAX_SKILL_READS=3"
set "AGENT_TARGET=codex"
set "BUNDLE_NAME="
set "ADAPTER_OUTPUT=.agent"
set "UPGRADE=0"
set "UPDATE_SKILLS_REMOTE=0"
set "CLEAN_STALE=0"
set "FORCE=0"
set "SKIP_SUBMODULE=0"
set "SKIP_HEALTHCHECK=0"
set "DRY_RUN=0"
set "SKIP_GITNEXUS=0"
set "PYTHON_CMD="
set "ACTIVE_MODE="
set "STATE_FILE="
set "COMPILE_EXECUTED=0"
set "COPIED_FILES="
set "SKIPPED_FILES="

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--target" (
  set "TARGET_DIR=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--source-root" (
  set "SOURCE_ROOT=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--skills-url" (
  set "SKILLS_URL=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--skills-path" (
  set "SKILLS_PATH=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--profile" (
  set "PROFILE_PATH=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--max-skill-reads" (
  set "MAX_SKILL_READS=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--bundle" (
  set "BUNDLE_NAME=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--agent" (
  set "AGENT_TARGET=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--adapter-output" (
  set "ADAPTER_OUTPUT=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--upgrade" (
  set "UPGRADE=1"
  shift
  goto parse_args
)
if /I "%~1"=="--update-skills-remote" (
  set "UPDATE_SKILLS_REMOTE=1"
  shift
  goto parse_args
)
if /I "%~1"=="--clean-stale" (
  set "CLEAN_STALE=1"
  shift
  goto parse_args
)
if /I "%~1"=="--force" (
  set "FORCE=1"
  shift
  goto parse_args
)
if /I "%~1"=="--skip-submodule" (
  set "SKIP_SUBMODULE=1"
  shift
  goto parse_args
)
if /I "%~1"=="--skip-healthcheck" (
  set "SKIP_HEALTHCHECK=1"
  shift
  goto parse_args
)
if /I "%~1"=="--dry-run" (
  set "DRY_RUN=1"
  shift
  goto parse_args
)
if /I "%~1"=="--skip-gitnexus" (
  set "SKIP_GITNEXUS=1"
  shift
  goto parse_args
)
if /I "%~1"=="-h" goto usage
if /I "%~1"=="--help" goto usage
call :die Unknown option: %~1
exit /b 1

:args_done
if not exist "%TARGET_DIR%" call :die Target directory not found: %TARGET_DIR%
if not exist "%SOURCE_ROOT%" call :die Source root not found: %SOURCE_ROOT%
if defined PROFILE_PATH if defined BUNDLE_NAME call :die Use either --profile or --bundle/--agent options, not both.

if defined PROFILE_PATH set "ACTIVE_MODE=profile"
if defined BUNDLE_NAME set "ACTIVE_MODE=bundle"

set "STATE_FILE=%TARGET_DIR%\%ADAPTER_OUTPUT%\bootstrap.state.json"

if "%UPGRADE%"=="1" (
  set "FORCE=1"
  if not "%CLEAN_STALE%"=="1" set "CLEAN_STALE=1"
  if not defined ACTIVE_MODE (
    call :resolve_upgrade_mode_from_state
    if errorlevel 1 exit /b 1
  )
)

call :is_integer "%MAX_SKILL_READS%"
if errorlevel 1 call :die --max-skill-reads must be an integer
if %MAX_SKILL_READS% LSS 1 set "MAX_SKILL_READS=1"
if /I not "%AGENT_TARGET%"=="codex" if /I not "%AGENT_TARGET%"=="copilot" if /I not "%AGENT_TARGET%"=="gemini" if /I not "%AGENT_TARGET%"=="all" (
  call :die --agent must be one of: codex^|copilot^|gemini^|all
)
if /I "%ACTIVE_MODE%"=="profile" if not defined PROFILE_PATH call :die Profile mode requires --profile.
if /I "%ACTIVE_MODE%"=="bundle" if not defined BUNDLE_NAME call :die Bundle mode requires --bundle.

call :log Target: %TARGET_DIR%
call :log Source root: %SOURCE_ROOT%
call :log Guardrail max-skill-reads: %MAX_SKILL_READS%
if "%UPGRADE%"=="1" call :log Upgrade mode enabled.
if "%UPDATE_SKILLS_REMOTE%"=="1" call :log Skills remote update enabled.
if "%CLEAN_STALE%"=="1" call :log Stale generated file cleanup enabled.
if defined PROFILE_PATH call :log Profile mode enabled: profile=%PROFILE_PATH%
if defined BUNDLE_NAME call :log Bundle compile enabled: bundle=%BUNDLE_NAME%, agent=%AGENT_TARGET%, output=%ADAPTER_OUTPUT%

call :setup_submodule
set "RELATIVE_PATH=AGENTS.md"
call :copy_template_file
set "RELATIVE_PATH=skill_scheduler.py"
call :copy_template_file
set "RELATIVE_PATH=services\skill_scheduler.py"
call :copy_template_file
set "RELATIVE_PATH=tests\test_skill_scheduler.py"
call :copy_template_file
if defined PROFILE_PATH goto run_profile_mode
call :run_adapter_compile
goto after_compile_mode
:run_profile_mode
call :run_profile_apply
:after_compile_mode
call :persist_bootstrap_state
call :setup_gitnexus
call :run_health_check
call :setup_git_exclude

call :log Bootstrap complete.
if defined COPIED_FILES (
  call :log Copied files:
  set "COPIED_LIST=!COPIED_FILES!"
  set "COPIED_LIST=!COPIED_LIST:;= !"
  for %%F in (!COPIED_LIST!) do echo   - %%F
)
if defined SKIPPED_FILES (
  call :warn Skipped existing files:
  set "SKIPPED_LIST=!SKIPPED_FILES!"
  set "SKIPPED_LIST=!SKIPPED_LIST:;= !"
  for %%F in (!SKIPPED_LIST!) do >&2 echo   - %%F
)
exit /b 0

:usage
echo Usage:
echo   tools\bootstrap_agent.bat [options]
echo.
echo Options:
echo   --target ^<dir^>            Target project directory ^(default: current directory^)
echo   --source-root ^<dir^>       Source template root ^(default: parent of this script^)
echo   --skills-url ^<url^>        my-agent-skills git URL
echo                             ^(default: https://github.com/Alanlee0323/my-agent-skills.git^)
echo   --skills-path ^<path^>      Submodule path in target repo ^(default: my-agent-skills^)
echo   --profile ^<path^>          Agent profile yaml path ^(relative to target or absolute^)
echo   --max-skill-reads ^<n^>     Guardrail value used for health check ^(default: 3^)
echo   --bundle ^<name^>           Bundle name from my-agent-skills\bundles\^<name^>.yaml
echo   --agent ^<name^>            Adapter target: codex^|copilot^|gemini^|all ^(default: codex^)
echo   --adapter-output ^<path^>   Output directory for compiled adapter artifacts ^(default: .agent^)
echo   --upgrade                   Re-apply bootstrap using previous state ^(forces overwrite^)
echo   --update-skills-remote      Update my-agent-skills to latest remote commit
echo   --clean-stale               Remove stale generated files tracked by previous state
echo   --force                     Overwrite existing target files
echo   --skip-submodule            Skip submodule add/update
echo   --skip-healthcheck          Skip scheduler health check
echo   --skip-gitnexus             Skip GitNexus analyze step
echo   --dry-run                   Print actions without applying changes
echo   -h, --help                  Show this help
echo.
echo Examples:
echo   tools\bootstrap_agent.bat --target C:\path\to\project
echo   tools\bootstrap_agent.bat --target . --force
echo   tools\bootstrap_agent.bat --target . --dry-run
echo   tools\bootstrap_agent.bat --target . --bundle engineer --agent codex
echo   tools\bootstrap_agent.bat --target . --profile agent.profile.yaml
echo   tools\bootstrap_agent.bat --target . --upgrade --update-skills-remote
exit /b 0

:log
echo [bootstrap] %*
exit /b 0

:warn
>&2 echo [bootstrap][warn] %*
exit /b 0

:die
>&2 echo [bootstrap][error] %*
exit /b 1

:is_integer
set "VAL=%~1"
if "%VAL%"=="" exit /b 1
for /f "delims=0123456789" %%A in ("%VAL%") do exit /b 1
exit /b 0

:copy_template_file
if not "%~1"=="" set "RELATIVE_PATH=%~1"
if not defined RELATIVE_PATH call :die Missing RELATIVE_PATH for copy_template_file.
set "SRC=%SOURCE_ROOT%\%RELATIVE_PATH%"
set "DST=%TARGET_DIR%\%RELATIVE_PATH%"

if not exist "%SRC%" call :die Template file not found: %SRC%
for %%I in ("%DST%") do set "DST_DIR=%%~dpI"
if not exist "%DST_DIR%" (
  if "%DRY_RUN%"=="1" (
    echo + mkdir "%DST_DIR%"
  ) else (
    mkdir "%DST_DIR%" || call :die Failed to create directory: %DST_DIR%
  )
)

if exist "%DST%" if not "%FORCE%"=="1" (
  >&2 echo [bootstrap][warn] Skip existing file ^(use --force to overwrite^): %DST%
  if defined SKIPPED_FILES (
    set "SKIPPED_FILES=!SKIPPED_FILES!;%RELATIVE_PATH%"
  ) else (
    set "SKIPPED_FILES=%RELATIVE_PATH%"
  )
  exit /b 0
)

if "%DRY_RUN%"=="1" (
  echo + copy /Y "%SRC%" "%DST%"
) else (
  copy /Y "%SRC%" "%DST%" >nul || call :die Failed to copy file: %RELATIVE_PATH%
)
if defined COPIED_FILES (
  set "COPIED_FILES=!COPIED_FILES!;%RELATIVE_PATH%"
) else (
  set "COPIED_FILES=%RELATIVE_PATH%"
)
exit /b 0

:setup_submodule
if "%SKIP_SUBMODULE%"=="1" (
  call :log Skip submodule setup by request.
  exit /b 0
)

set "SKILLS_ABS=%TARGET_DIR%\%SKILLS_PATH%"

git -C "%TARGET_DIR%" rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  call :warn Target is not a git repo. Falling back to git clone.
  if exist "%SKILLS_ABS%" (
    call :log Skills path already exists. Skip clone.
    if "%UPDATE_SKILLS_REMOTE%"=="1" if exist "%SKILLS_ABS%\.git" (
      if "%DRY_RUN%"=="1" (
        echo + git -C "%SKILLS_ABS%" pull --ff-only
      ) else (
        git -C "%SKILLS_ABS%" pull --ff-only
        if errorlevel 1 call :warn Skills remote pull failed. Please inspect manually.
      )
    )
    exit /b 0
  )
  if "%DRY_RUN%"=="1" (
    echo + git clone "%SKILLS_URL%" "%SKILLS_ABS%"
  ) else (
    git clone "%SKILLS_URL%" "%SKILLS_ABS%"
    if errorlevel 1 call :warn git clone failed. Please inspect manually.
  )
  exit /b 0
)

if exist "%SKILLS_ABS%" (
  call :log my-agent-skills path exists. Running submodule update.
) else (
  call :log Adding my-agent-skills submodule: %SKILLS_URL% -^> %SKILLS_PATH%
  if "%DRY_RUN%"=="1" (
    echo + git -C "%TARGET_DIR%" submodule add "%SKILLS_URL%" "%SKILLS_PATH%"
  ) else (
    git -C "%TARGET_DIR%" submodule add "%SKILLS_URL%" "%SKILLS_PATH%" >nul 2>&1
    if errorlevel 1 call :warn Submodule add failed. Continue to update step.
  )
)

if "%DRY_RUN%"=="1" (
  echo + git -C "%TARGET_DIR%" submodule update --init --recursive "%SKILLS_PATH%"
) else (
  git -C "%TARGET_DIR%" submodule update --init --recursive "%SKILLS_PATH%"
  if errorlevel 1 call :warn Submodule update failed. Please inspect manually.
)

if "%UPDATE_SKILLS_REMOTE%"=="1" (
  if "%DRY_RUN%"=="1" (
    echo + git -C "%TARGET_DIR%" submodule update --init --remote --recursive "%SKILLS_PATH%"
  ) else (
    git -C "%TARGET_DIR%" submodule update --init --remote --recursive "%SKILLS_PATH%"
    if errorlevel 1 call :warn Submodule remote update failed. Please inspect manually.
  )
)
exit /b 0

:setup_gitnexus
if "%SKIP_GITNEXUS%"=="1" (
  call :log Skip GitNexus setup by request.
  exit /b 0
)
git -C "%TARGET_DIR%" rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  call :warn Target is not a git repo. Skip GitNexus analyze.
  exit /b 0
)
where npx >nul 2>&1
if errorlevel 1 (
  call :warn npx not found. Skip GitNexus analyze. Install Node.js to enable.
  exit /b 0
)
call :log Running GitNexus analyze on target repo.
if "%DRY_RUN%"=="1" (
  echo + npx gitnexus analyze "%TARGET_DIR%"
  exit /b 0
)
call npx gitnexus analyze "%TARGET_DIR%"
if errorlevel 1 call :warn GitNexus analyze failed. Please inspect manually.
exit /b 0

:setup_git_exclude
git -C "%TARGET_DIR%" rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 exit /b 0
set "EXCLUDE_FILE=%TARGET_DIR%\.git\info\exclude"
set "EXCLUDE_DIR=%TARGET_DIR%\.git\info"
if not exist "%EXCLUDE_DIR%" mkdir "%EXCLUDE_DIR%"
set "MARKER=# Bootstrap agent tools"
findstr /C:"%MARKER%" "%EXCLUDE_FILE%" >nul 2>&1
if not errorlevel 1 (
  call :log Git exclude entries already present. Skip.
  exit /b 0
)
call :log Writing agent paths to .git/info/exclude.
if "%DRY_RUN%"=="1" (
  echo + append to %EXCLUDE_FILE%
  exit /b 0
)
(
  echo.
  echo # Bootstrap agent tools
  echo AGENTS.md
  echo CLAUDE.md
  echo skill_scheduler.py
  echo services/skill_scheduler.py
  echo tests/test_skill_scheduler.py
  echo my-agent-skills/
  echo skills/
  echo .gitnexus/
) >> "%EXCLUDE_FILE%"
exit /b 0

:resolve_python_cmd
if defined PYTHON_CMD exit /b 0
set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py -3"
  exit /b 0
)
where python >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  exit /b 0
)
where python3 >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=python3"
  exit /b 0
)
exit /b 0

:resolve_upgrade_mode_from_state
call :resolve_python_cmd
if not defined PYTHON_CMD (
  call :die No python interpreter found; cannot resolve --upgrade mode.
  exit /b 1
)
set "STATE_TOOL=%SOURCE_ROOT%\tools\bootstrap_state.py"
if not exist "%STATE_TOOL%" (
  call :die State helper not found: %STATE_TOOL%
  exit /b 1
)

set "STATE_TMP=%TEMP%\bootstrap_state_%RANDOM%_%RANDOM%.txt"
%PYTHON_CMD% "%STATE_TOOL%" resolve --state "%STATE_FILE%" --discover-root "%TARGET_DIR%" > "%STATE_TMP%" 2>nul
if errorlevel 1 (
  if exist "%STATE_TMP%" del /q "%STATE_TMP%" >nul 2>&1
  call :die --upgrade requested but no previous bootstrap state found. Provide --profile or --bundle explicitly.
  exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in ("%STATE_TMP%") do (
  if /I "%%A"=="STATE_FILE" set "STATE_FILE=%%B"
  if /I "%%A"=="MODE" set "ACTIVE_MODE=%%B"
  if /I "%%A"=="PROFILE_PATH" set "PROFILE_PATH=%%B"
  if /I "%%A"=="BUNDLE_NAME" set "BUNDLE_NAME=%%B"
  if /I "%%A"=="AGENT_TARGET" set "AGENT_TARGET=%%B"
  if /I "%%A"=="ADAPTER_OUTPUT" set "ADAPTER_OUTPUT=%%B"
  if /I "%%A"=="SKILLS_PATH" set "SKILLS_PATH=%%B"
  if /I "%%A"=="MAX_SKILL_READS" set "MAX_SKILL_READS=%%B"
)
if exist "%STATE_TMP%" del /q "%STATE_TMP%" >nul 2>&1

if not defined ACTIVE_MODE (
  call :die Resolved state is missing mode. Provide --profile or --bundle explicitly.
  exit /b 1
)
if /I "%ACTIVE_MODE%"=="profile" if not defined PROFILE_PATH (
  call :die Resolved state mode is profile, but profile path is missing.
  exit /b 1
)
if /I "%ACTIVE_MODE%"=="bundle" if not defined BUNDLE_NAME (
  call :die Resolved state mode is bundle, but bundle name is missing.
  exit /b 1
)
call :log Upgrade mode restored from state: mode=%ACTIVE_MODE%, output=%ADAPTER_OUTPUT%
exit /b 0

:run_health_check
if "%SKIP_HEALTHCHECK%"=="1" (
  call :log Skip health check by request.
  exit /b 0
)

call :resolve_python_cmd
if not defined PYTHON_CMD (
  call :warn No python interpreter found. Skip health check.
  exit /b 0
)

set "SCHEDULER=%TARGET_DIR%\skill_scheduler.py"
if not exist "%SCHEDULER%" (
  call :warn Missing scheduler file: %SCHEDULER%. Skip health check.
  exit /b 0
)

call :log Running scheduler health check.
if "%DRY_RUN%"=="1" (
  echo + %PYTHON_CMD% "%SCHEDULER%" --task "health check" --top 1 --max-skill-reads "%MAX_SKILL_READS%" --format text
  exit /b 0
)

%PYTHON_CMD% "%SCHEDULER%" --task "health check" --top 1 --max-skill-reads "%MAX_SKILL_READS%" --format text
if errorlevel 1 call :warn Health check failed. Please inspect manually.
exit /b 0

:run_adapter_compile
if not defined BUNDLE_NAME (
  call :log No bundle specified. Skip adapter compile.
  exit /b 0
)

call :resolve_python_cmd
if not defined PYTHON_CMD call :die No python interpreter found; cannot compile adapter artifacts.

set "COMPILER=%SOURCE_ROOT%\tools\compile_agent_bundle.py"
if not exist "%COMPILER%" call :die Bundle compiler not found: %COMPILER%

set "SKILLS_REPO=%TARGET_DIR%\%SKILLS_PATH%"
if not exist "%SKILLS_REPO%" if not "%DRY_RUN%"=="1" call :die Skills repo path not found for compile: %SKILLS_REPO%
if not exist "%SKILLS_REPO%" if "%DRY_RUN%"=="1" call :warn Skills repo path not found in dry-run; command will still be printed: %SKILLS_REPO%

set "ADAPTER_OUTPUT_ABS=%TARGET_DIR%\%ADAPTER_OUTPUT%"
call :log Compiling adapter artifacts ^(agent=%AGENT_TARGET%, bundle=%BUNDLE_NAME%^).
if "%DRY_RUN%"=="1" (
  echo + %PYTHON_CMD% "%COMPILER%" --agent "%AGENT_TARGET%" --bundle "%BUNDLE_NAME%" --skills-repo "%SKILLS_REPO%" --output "%ADAPTER_OUTPUT_ABS%" --project-root "%TARGET_DIR%" --max-skill-reads "%MAX_SKILL_READS%"
  set "COMPILE_EXECUTED=1"
  set "ACTIVE_MODE=bundle"
  exit /b 0
)

%PYTHON_CMD% "%COMPILER%" --agent "%AGENT_TARGET%" --bundle "%BUNDLE_NAME%" --skills-repo "%SKILLS_REPO%" --output "%ADAPTER_OUTPUT_ABS%" --project-root "%TARGET_DIR%" --max-skill-reads "%MAX_SKILL_READS%"
if errorlevel 1 call :die Adapter compile failed.
set "COMPILE_EXECUTED=1"
set "ACTIVE_MODE=bundle"
exit /b 0

:run_profile_apply
if not defined PROFILE_PATH exit /b 0

call :resolve_python_cmd
if not defined PYTHON_CMD call :die No python interpreter found; cannot apply profile.

set "APPLIER=%SOURCE_ROOT%\tools\apply_agent_profile.py"
if not exist "%APPLIER%" call :die Profile applier not found: %APPLIER%

set "PROFILE_ABS=%PROFILE_PATH%"
if not exist "%PROFILE_ABS%" set "PROFILE_ABS=%TARGET_DIR%\%PROFILE_PATH%"
if not exist "%PROFILE_ABS%" if not "%DRY_RUN%"=="1" call :die Profile file not found: %PROFILE_ABS%
if not exist "%PROFILE_ABS%" if "%DRY_RUN%"=="1" call :warn Profile file not found in dry-run; command will still be printed: %PROFILE_ABS%

set "SKILLS_REPO=%TARGET_DIR%\%SKILLS_PATH%"
call :log Applying agent profile: %PROFILE_ABS%
if "%DRY_RUN%"=="1" (
  echo + %PYTHON_CMD% "%APPLIER%" --profile "%PROFILE_ABS%" --project-root "%TARGET_DIR%" --default-skills-repo "%SKILLS_REPO%" --template-root "%SOURCE_ROOT%\adapters"
  set "COMPILE_EXECUTED=1"
  set "ACTIVE_MODE=profile"
  exit /b 0
)

%PYTHON_CMD% "%APPLIER%" --profile "%PROFILE_ABS%" --project-root "%TARGET_DIR%" --default-skills-repo "%SKILLS_REPO%" --template-root "%SOURCE_ROOT%\adapters"
if errorlevel 1 call :die Profile apply failed.
set "COMPILE_EXECUTED=1"
set "ACTIVE_MODE=profile"
exit /b 0

:persist_bootstrap_state
if not "%COMPILE_EXECUTED%"=="1" exit /b 0

call :resolve_python_cmd
if not defined PYTHON_CMD (
  call :warn No python interpreter found. Skip bootstrap state update.
  exit /b 0
)
set "STATE_TOOL=%SOURCE_ROOT%\tools\bootstrap_state.py"
if not exist "%STATE_TOOL%" (
  call :warn State helper not found: %STATE_TOOL%. Skip state update.
  exit /b 0
)

set "ADAPTER_OUTPUT_ABS=%TARGET_DIR%\%ADAPTER_OUTPUT%"
if not defined STATE_FILE set "STATE_FILE=%ADAPTER_OUTPUT_ABS%\bootstrap.state.json"

call :log Updating bootstrap state: %STATE_FILE%
if "%DRY_RUN%"=="1" (
  echo + %PYTHON_CMD% "%STATE_TOOL%" reconcile --state "%STATE_FILE%" --output-root "%ADAPTER_OUTPUT_ABS%" --mode "%ACTIVE_MODE%" --project-root "%TARGET_DIR%" --adapter-output "%ADAPTER_OUTPUT%" --skills-path "%SKILLS_PATH%" --max-skill-reads "%MAX_SKILL_READS%"
  exit /b 0
)

if /I "%ACTIVE_MODE%"=="profile" (
  if "%CLEAN_STALE%"=="1" (
    %PYTHON_CMD% "%STATE_TOOL%" reconcile --state "%STATE_FILE%" --output-root "%ADAPTER_OUTPUT_ABS%" --mode "%ACTIVE_MODE%" --project-root "%TARGET_DIR%" --profile-path "%PROFILE_PATH%" --adapter-output "%ADAPTER_OUTPUT%" --skills-path "%SKILLS_PATH%" --max-skill-reads "%MAX_SKILL_READS%" --clean-stale
  ) else (
    %PYTHON_CMD% "%STATE_TOOL%" reconcile --state "%STATE_FILE%" --output-root "%ADAPTER_OUTPUT_ABS%" --mode "%ACTIVE_MODE%" --project-root "%TARGET_DIR%" --profile-path "%PROFILE_PATH%" --adapter-output "%ADAPTER_OUTPUT%" --skills-path "%SKILLS_PATH%" --max-skill-reads "%MAX_SKILL_READS%"
  )
) else (
  if "%CLEAN_STALE%"=="1" (
    %PYTHON_CMD% "%STATE_TOOL%" reconcile --state "%STATE_FILE%" --output-root "%ADAPTER_OUTPUT_ABS%" --mode "%ACTIVE_MODE%" --bundle-name "%BUNDLE_NAME%" --agent-target "%AGENT_TARGET%" --project-root "%TARGET_DIR%" --adapter-output "%ADAPTER_OUTPUT%" --skills-path "%SKILLS_PATH%" --max-skill-reads "%MAX_SKILL_READS%" --clean-stale
  ) else (
    %PYTHON_CMD% "%STATE_TOOL%" reconcile --state "%STATE_FILE%" --output-root "%ADAPTER_OUTPUT_ABS%" --mode "%ACTIVE_MODE%" --bundle-name "%BUNDLE_NAME%" --agent-target "%AGENT_TARGET%" --project-root "%TARGET_DIR%" --adapter-output "%ADAPTER_OUTPUT%" --skills-path "%SKILLS_PATH%" --max-skill-reads "%MAX_SKILL_READS%"
  )
)
if errorlevel 1 call :warn Bootstrap state update failed.
exit /b 0
