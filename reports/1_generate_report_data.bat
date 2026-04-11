@echo off
setlocal

REM ============================
REM Paths
REM ============================
set "NEW_JSON=E:\Github\RSDWArchive\0.11.0.8\json"
set "OLD_JSON=E:\Github\0.11.0.3\json"

set "NEW_TEXTURES=E:\Github\RSDWArchive\0.11.0.8\textures"
set "OLD_TEXTURES=E:\Github\0.11.0.3\textures"

REM Output folder = same folder as this .bat, inside /reports
set "OUT_DIR=%~dp0reports"

if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

:menu
cls
echo ==========================================
echo      JSON + TEXTURE DIFF REPORT TOOL
echo ==========================================
echo.
echo Comparing: 0.11.0.3  --^>  0.11.0.8
echo.
echo JSON Old:      %OLD_JSON%
echo JSON New:      %NEW_JSON%
echo.
echo Textures Old:  %OLD_TEXTURES%
echo Textures New:  %NEW_TEXTURES%
echo.
echo Output:        %OUT_DIR%
echo.
echo 1. JSON name-status report
echo 2. JSON numstat report
echo 3. JSON full diff report
echo 4. Texture name-status report
echo 5. Run all recommended reports
echo 6. Open output folder
echo 7. Exit
echo.
set /p "choice=Choose an option: "

if "%choice%"=="1" goto json_name_status
if "%choice%"=="2" goto json_numstat
if "%choice%"=="3" goto json_full_diff
if "%choice%"=="4" goto textures_name_status
if "%choice%"=="5" goto all_reports
if "%choice%"=="6" goto open_folder
if "%choice%"=="7" goto end

echo.
echo Invalid choice.
pause
goto menu

:json_name_status
echo.
echo Creating JSON name-status report...
git diff --no-index -M --name-status "%OLD_JSON%" "%NEW_JSON%" > "%OUT_DIR%\json_name_status_report.txt"
echo Done: "%OUT_DIR%\json_name_status_report.txt"
pause
goto menu

:json_numstat
echo.
echo Creating JSON numstat report...
git diff --no-index -M --numstat "%OLD_JSON%" "%NEW_JSON%" > "%OUT_DIR%\json_numstat_report.txt"
echo Done: "%OUT_DIR%\json_numstat_report.txt"
pause
goto menu

:json_full_diff
echo.
echo Creating JSON full diff report...
git diff --no-index -M "%OLD_JSON%" "%NEW_JSON%" > "%OUT_DIR%\json_full_diff_report.txt"
echo Done: "%OUT_DIR%\json_full_diff_report.txt"
pause
goto menu

:textures_name_status
echo.
echo Creating texture name-status report...
git diff --no-index -M --name-status "%OLD_TEXTURES%" "%NEW_TEXTURES%" > "%OUT_DIR%\textures_name_status_report.txt"
echo Done: "%OUT_DIR%\textures_name_status_report.txt"
pause
goto menu

:all_reports
echo.
echo Creating all recommended reports...

git diff --no-index -M --name-status "%OLD_JSON%" "%NEW_JSON%" > "%OUT_DIR%\json_name_status_report.txt"
git diff --no-index -M --numstat "%OLD_JSON%" "%NEW_JSON%" > "%OUT_DIR%\json_numstat_report.txt"
git diff --no-index -M "%OLD_JSON%" "%NEW_JSON%" > "%OUT_DIR%\json_full_diff_report.txt"
git diff --no-index -M --name-status "%OLD_TEXTURES%" "%NEW_TEXTURES%" > "%OUT_DIR%\textures_name_status_report.txt"

echo.
echo Running Python processing...

python 2_create_reports.py
python 3_create_changelog.py

echo.
echo Done.
echo Files created in: "%OUT_DIR%"
pause
goto menu

:end
endlocal
exit