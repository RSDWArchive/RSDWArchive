@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "PYWIKIBOT_DIR=%SCRIPT_DIR%"
set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "PUBLISH_SCRIPT=%SCRIPT_DIR%scripts\publish_pages.py"
set "ITEMS_JSON=%SCRIPT_DIR%pages\pages.items.json"
set "NPCS_JSON=%SCRIPT_DIR%pages\pages.npcs.json"
set "INDEX_JSON=%SCRIPT_DIR%pages\pages.sandbox-index.json"
set "FAMILY=rsdwwiki"
set "LANG=en"

set "MAX_PAGES=%~1"
if "%MAX_PAGES%"=="" set "MAX_PAGES=0"

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Virtual environment python not found: "%PYTHON_EXE%"
  echo Create it first with: python -m venv .venv
  pause
  exit /b 1
)

if not exist "%PUBLISH_SCRIPT%" (
  echo [ERROR] publish script not found: "%PUBLISH_SCRIPT%"
  pause
  exit /b 1
)

if not exist "%ITEMS_JSON%" (
  echo [ERROR] Missing pages file: "%ITEMS_JSON%"
  pause
  exit /b 1
)

if not exist "%NPCS_JSON%" (
  echo [ERROR] Missing pages file: "%NPCS_JSON%"
  pause
  exit /b 1
)

if not exist "%INDEX_JSON%" (
  echo [ERROR] Missing pages file: "%INDEX_JSON%"
  echo Run run_generation_pipeline.py first.
  pause
  exit /b 1
)

echo [WARN] This will perform LIVE wiki edits.
echo [WARN] Target files:
echo        - %ITEMS_JSON%
echo        - %NPCS_JSON%
echo        - %INDEX_JSON%
echo [WARN] Max pages per file: %MAX_PAGES% (0 means all pages)
echo.
set /p CONFIRM=Type YES to continue: 
if /I not "%CONFIRM%"=="YES" (
  echo [INFO] Publish cancelled.
  pause
  exit /b 0
)

echo [INFO] Publishing items...
"%PYTHON_EXE%" "%PUBLISH_SCRIPT%" --pages "%ITEMS_JSON%" --family "%FAMILY%" --lang "%LANG%" --max-pages %MAX_PAGES%
if errorlevel 1 (
  echo [ERROR] Live publish failed while publishing items.
  pause
  exit /b 1
)

echo [INFO] Publishing npcs...
"%PYTHON_EXE%" "%PUBLISH_SCRIPT%" --pages "%NPCS_JSON%" --family "%FAMILY%" --lang "%LANG%" --max-pages %MAX_PAGES%
if errorlevel 1 (
  echo [ERROR] Live publish failed while publishing npcs.
  pause
  exit /b 1
)

echo [INFO] Publishing sandbox index...
"%PYTHON_EXE%" "%PUBLISH_SCRIPT%" --pages "%INDEX_JSON%" --family "%FAMILY%" --lang "%LANG%" --max-pages 1
if errorlevel 1 (
  echo [ERROR] Live publish failed while publishing sandbox index.
  pause
  exit /b 1
)

echo [OK] Live publish complete.
pause
exit /b 0
