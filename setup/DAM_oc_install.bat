@echo off
REM DAM Windows installation. Idempotent: safe to run on every boot.
REM Lives in setup\; resolves the repo root itself, so it works from anywhere.
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

set "VER="
for /F "tokens=2 delims=:" %%v in ('findstr /C:"\"version\"" "%ROOT%\frontend\package.json"') do if not defined VER set "VER=%%v"
set "VER=%VER:"=%"
set "VER=%VER:,=%"
set "VER=%VER: =%"

echo ===========================================
echo DAM v%VER% - Windows Installation
echo ===========================================
echo.

where ffmpeg >nul 2>&1 || echo WARNING: ffmpeg is not on PATH. Video thumbnails and video face scanning need it.

echo ^>^> Setting up the engine...
cd /d "%ROOT%\backend"
if not exist venv python -m venv venv
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: engine installation failed.
    exit /b 1
)
pip install -r requirements-dev.txt
if not exist models mkdir models
if not exist models\face_detection_yunet_2023mar.onnx curl -fSL -o models\face_detection_yunet_2023mar.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
if not exist models\face_recognition_sface_2021dec.onnx curl -fSL -o models\face_recognition_sface_2021dec.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx

echo.
echo ^>^> Setting up the interface...
cd /d "%ROOT%\frontend"
call npm install
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: interface installation failed.
    exit /b 1
)

cd /d "%ROOT%"
echo.
echo ===========================================
echo Installation complete
echo ===========================================
echo.
echo Next steps:
echo   1. Run: DAM.bat   (installs what is missing, boots both halves, opens http://127.0.0.1:5173)
echo   2. Optional settings: copy backend\.env.example to backend\.env
echo.
endlocal
exit /b 0
