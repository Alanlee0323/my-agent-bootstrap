@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "SOURCE_ROOT=%%~fI"
set "TARGET_DIR=%CD%"
set "SKILLS_URL=https://github.com/Alanlee0323/my-agent-skills.git"
set "SKILLS_PATH=my-agent-skills"
set "MAX_SKILL_READS=3"
set "FORCE=0"
set "SKIP_SUBMODULE=0"
set "SKIP_HEALTHCHECK=0"
set "DRY_RUN=0"
set "SKIP_GITNEXUS=0"
set "PYTHON_CMD="
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
if /I "%~1"=="--max-skill-reads" (
  set "MAX_SKILL_READS=%~2"
  shift
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
call :is_integer "%MAX_SKILL_READS%"
if errorlevel 1 call :die --max-skill-reads must be an integer
if %MAX_SKILL_READS% LSS 1 set "MAX_SKILL_READS=1"

call :log Target: %TARGET_DIR%
call :log Source root: %SOURCE_ROOT%
call :log Guardrail max-skill-reads: %MAX_SKILL_READS%

call :setup_submodule
call :copy_template_file AGENTS.md
call :copy_template_file skill_scheduler.py
call :copy_template_file services\skill_scheduler.py
call :copy_template_file tests\test_skill_scheduler.py
call :setup_gitnexus
call :run_health_check
call :setup_git_exclude

call :log Bootstrap complete.
if defined COPIED_FILES (
  call :log Copied files:
  for %%F in (!COPIED_FILES:;= !) do echo   - %%F
)
if defined SKIPPED_FILES (
  call :warn Skipped existing files:
  for %%F in (!SKIPPED_FILES:;= !) do >&2 echo   - %%F
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
echo   --max-skill-reads ^<n^>     Guardrail value used for health check ^(default: 3^)
echo   --force                   Overwrite existing target files
echo   --skip-submodule          Skip submodule add/update
echo   --skip-healthcheck        Skip scheduler health check
echo   --skip-gitnexus           Skip GitNexus analyze step
echo   --dry-run                 Print actions without applying changes
echo   -h, --help                Show this help
echo.
echo Examples:
echo   tools\bootstrap_agent.bat --target C:\path\to\project
echo   tools\bootstrap_agent.bat --target . --force
echo   tools\bootstrap_agent.bat --target . --dry-run
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

:append_list
set "LIST_NAME=%~1"
set "LIST_VALUE=%~2"
if defined %LIST_NAME% (
  set "%LIST_NAME%=!%LIST_NAME%!;%LIST_VALUE%"
) else (
  set "%LIST_NAME%=%LIST_VALUE%"
)
exit /b 0

:copy_template_file
set "RELATIVE_PATH=%~1"
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
  call :warn Skip existing file ^(use --force to overwrite^): %DST%
  call :append_list SKIPPED_FILES "%RELATIVE_PATH%"
  exit /b 0
)

if "%DRY_RUN%"=="1" (
  echo + copy /Y "%SRC%" "%DST%"
) else (
  copy /Y "%SRC%" "%DST%" >nul || call :die Failed to copy file: %RELATIVE_PATH%
)
call :append_list COPIED_FILES "%RELATIVE_PATH%"
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
