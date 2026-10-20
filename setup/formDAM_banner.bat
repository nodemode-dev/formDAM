@echo off
REM formDAM_banner.bat - boot banner for formDAM (Windows): the formDAM icon in ASCII, not the word.
REM Self-contained: pure cmd. Mirrors setup/formDAM_banner at its 28-column size.
REM   FORMDAM_BANNER=0            suppress the banner
REM   NO_COLOR=1                  monochrome
REM   FORMDAM_VERSION=v1.13.9     version shown under the icon (default: frontend\package.json)
setlocal EnableDelayedExpansion
if "%FORMDAM_BANNER%"=="0" exit /b 0

set "ROOT=%~dp0.."
set "D=" & set "R=" & set "C0=" & set "C1=" & set "C2=" & set "C3=" & set "C4=" & set "C5=" & set "C6=" & set "C7="
if not defined NO_COLOR (
    for /F "delims=" %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
    set "D=!ESC![38;2;115;115;115m"
    set "R=!ESC![0m"
    set "C0=!ESC![38;2;255;231;88m"
    set "C1=!ESC![38;2;255;204;82m"
    set "C2=!ESC![38;2;255;177;76m"
    set "C3=!ESC![38;2;255;150;70m"
    set "C4=!ESC![38;2;255;123;63m"
    set "C5=!ESC![38;2;255;96;57m"
    set "C6=!ESC![38;2;255;69;51m"
    set "C7=!ESC![38;2;255;41;44m"
)

set "VER=%FORMDAM_VERSION%"
if not defined VER if exist "%ROOT%\frontend\package.json" (
    for /F "tokens=2 delims=:" %%v in ('findstr /C:"\"version\"" "%ROOT%\frontend\package.json"') do (
        if not defined VER set "VER=%%v"
    )
    if defined VER (
        set "VER=!VER:"=!"
        set "VER=!VER:,=!"
        set "VER=!VER: =!"
        set "VER=v!VER!"
    )
)

echo.
echo   !D!.-''-._!R!
echo  !D!/      `-._!R!
echo !D!^|  !C3!d!C2!88888!C1!b !D!`-._!R!
echo !D!^| !C3!d888!C2!88888!C1!88b !D!`-._!R!
echo !D!^| !C4!8!C3!88888!C2!88888!C1!888b  !D!`-._!R!
echo !D!^| !C4!888!C3!88P Y!C2!88888!C1!88888!C0!b !D!`-._!R!
echo !D!^| !C4!88888   !C3!88!C2!88888!C1!88888!C0!8b !D!`-.!R!
echo !D!^| !C5!88!C4!888   !C3!8888!C2!8P Y8!C1!8888!C0!8   !D!)!R!
echo !D!^| !C5!8888!C4!8   8!C3!8888   !C2!888!C1!88P !D!.-'!R!
echo !D!^| !C6!Y!C5!888P   !C4!888!C3!88   !C2!Y8P !D!_.-'!R!
echo !D!^|         !C4!Y888P    !D!_.-'!R!
echo !D!^| !C7!d!C6!888b        !D!_.-'!R!
echo !D!^| !C7!Y8!C6!88P    !D!_.-'!R!
echo  !D!\      _.-'!R!
echo   !D!'-..-'`!R!
echo !D!----------------------------!R!
if defined VER (
    echo !D!photo ^& video library  ^|  !VER!!R!
) else (
    echo !D!photo ^& video library!R!
)
echo.
endlocal
exit /b 0
