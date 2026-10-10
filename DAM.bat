@echo off
REM DAM - Windows launcher for the local browser build. Banner, install (idempotent), boot.
REM Every step lives in setup\; this file only sequences them.
setlocal
cd /d "%~dp0"

REM Boot banner. Never allowed to fail the launch: cosmetics do not gate startup.
call setup\DAM_banner.bat

call setup\DAM_oc_install.bat
if %ERRORLEVEL% NEQ 0 (
    echo Installation failed; not booting.
    pause
    exit /b 1
)
call setup\DAM_boot.bat
endlocal
