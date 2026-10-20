@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "OPEN=0"
set "INSTALL=0"
for %%A in (%*) do (
  if /i "%%~A"=="--open" ( set "OPEN=1" ) else if /i "%%~A"=="--install" ( set "INSTALL=1" ) else if /i "%%~A"=="--help" ( goto :usage ) else if /i "%%~A"=="-h" ( goto :usage ) else ( call :usage & exit /b 2 )
)

echo.
echo [formDAM] == checking the tools
where python >nul 2>nul || ( echo [formDAM] Python 3.10 or newer is needed: https://www.python.org/downloads/ & exit /b 1 )
where node >nul 2>nul || ( echo [formDAM] Node 20.19 or 22.12 or newer is needed: https://nodejs.org & exit /b 1 )
where cargo >nul 2>nul || ( echo [formDAM] Rust is needed: https://rustup.rs & exit /b 1 )
where ffmpeg >nul 2>nul || echo [formDAM] ffmpeg is not on PATH; the app builds without it, but video thumbnails and video face scanning need it

echo.
echo [formDAM] == building the desktop app: models, window, frozen engine, installers
echo [formDAM] the first build compiles several hundred Rust crates
call setup\build_windows_app.bat || goto :failed

set "SETUP="
for %%F in ("src-tauri\target\release\bundle\nsis\*.exe") do set "SETUP=%%~fF"
echo.
echo [formDAM] done. The installers are in src-tauri\target\release\bundle (nsis and msi)
if "%INSTALL%"=="1" if defined SETUP ( echo [formDAM] running %SETUP% & start "" /wait "%SETUP%" )
if "%OPEN%"=="1" start "" "src-tauri\target\release\bundle"
exit /b 0

:failed
echo.
echo [formDAM] the build stopped at the step above; fix what it says and run build_app.bat again
exit /b 1

:usage
echo build_app.bat           build formDAM's desktop app on Windows, start to finish
echo   --install             run the NSIS installer when the build is done
echo   --open                open the folder with the installers when the build is done
exit /b 0
