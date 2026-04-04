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

echo [INFO] Running LIVE test publish for items (max 1)...
"%PYTHON_EXE%" "%PUBLISH_SCRIPT%" --pages "%ITEMS_JSON%" --family "%FAMILY%" --lang "%LANG%" --max-pages 1
if errorlevel 1 (
  echo [ERROR] Live test failed while publishing items.
  pause
  exit /b 1
)

echo [INFO] Running LIVE test publish for npcs (max 1)...
"%PYTHON_EXE%" "%PUBLISH_SCRIPT%" --pages "%NPCS_JSON%" --family "%FAMILY%" --lang "%LANG%" --max-pages 1
if errorlevel 1 (
  echo [ERROR] Live test failed while publishing npcs.
  pause
  exit /b 1
)

echo [INFO] Running LIVE test publish for sandbox index (max 1)...
"%PYTHON_EXE%" "%PUBLISH_SCRIPT%" --pages "%INDEX_JSON%" --family "%FAMILY%" --lang "%LANG%" --max-pages 1
if errorlevel 1 (
  echo [ERROR] Live test failed while publishing sandbox index.
  pause
  exit /b 1
)

echo [OK] Live publish test complete.
pause
exit /b 0
