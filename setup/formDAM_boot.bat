@echo off
REM formDAM boot (Windows): the engine and the interface, each in its own window, then the browser.
REM Lives in setup\; resolves the repo root itself.
setlocal EnableDelayedExpansion
set "ROOT=%~dp0.."
cd /d "%ROOT%"

set "VER="
for /F "tokens=2 delims=:" %%v in ('findstr /C:"\"version\"" "%ROOT%\frontend\package.json"') do if not defined VER set "VER=%%v"
set "VER=%VER:"=%"
set "VER=%VER:,=%"
set "VER=%VER: =%"
set "UI=http://127.0.0.1:5173"

echo ===========================================
echo formDAM v%VER% - Boot
echo ===========================================
echo.

if not exist "%ROOT%\backend\venv" (
    echo ERROR: the engine is not installed. Run setup\formDAM_oc_install.bat
    pause
    exit /b 1
)
if not exist "%ROOT%\frontend\node_modules" (
    echo ERROR: the interface is not installed. Run setup\formDAM_oc_install.bat
    pause
    exit /b 1
)

REM Settings reach the engine through the environment, never the interface.
if exist "%ROOT%\backend\.env" (
    for /F "usebackq tokens=1,* delims==" %%a in ("%ROOT%\backend\.env") do (
        echo %%a| findstr /b "#" >nul || if not "%%a"=="" set "%%a=%%b"
    )
)

for /f "usebackq delims=" %%k in (`""%ROOT%\backend\venv\Scripts\python.exe" -c "import secrets; print(secrets.token_hex(32))""`) do set "FORMDAM_SHELL_KEY=%%k"
set "UI_OPEN=%UI%/#dam-key=%FORMDAM_SHELL_KEY%"

echo Booting the engine...
start "formDAM engine" cmd /k "cd /d "%ROOT%\backend" && venv\Scripts\activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

timeout /t 2 /nobreak >nul

echo Booting the interface...
start "formDAM interface" cmd /k "cd /d "%ROOT%\frontend" && npm run dev"

echo.
echo ===========================================
echo     Services running:
echo     - Engine:    http://127.0.0.1:8000
echo     - Interface: %UI%
echo ===========================================
echo.
echo Close either window to stop that half.
echo A browser window opened here is connected to formDAM. To connect another one, open:
echo   %UI_OPEN%

if "%FORMDAM_OPEN%"=="0" goto done
set /a tries=0
:wait_ui
curl -s -o nul "%UI%" >nul 2>&1 && goto open_ui
set /a tries+=1
if !tries! GEQ 90 goto done
timeout /t 1 /nobreak >nul
goto wait_ui
:open_ui
start "" "%UI_OPEN%"
:done
endlocal
exit /b 0
