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
set CLIP_BASE=https://huggingface.co/onnx-community/CLIP-ViT-B-32-laion2B-s34B-b79K-ONNX/resolve/de693d0
if not exist models\clip_vit_b32_laion2b_int8.onnx curl -fSL -o models\clip_vit_b32_laion2b_int8.onnx %CLIP_BASE%/onnx/model_quantized.onnx
if not exist models\clip_vocab.json curl -fSL -o models\clip_vocab.json %CLIP_BASE%/vocab.json
if not exist models\clip_merges.txt curl -fSL -o models\clip_merges.txt %CLIP_BASE%/merges.txt
if not exist models\inpainting_lama_2025jan.onnx curl -fSL -o models\inpainting_lama_2025jan.onnx https://huggingface.co/opencv/inpainting_lama/resolve/aee6d22f0a13e5e35af1c9a1c3afd62841fc6f3f/inpainting_lama_2025jan.onnx
if not exist models\image_segmentation_efficientsam_ti_2025april.onnx curl -fSL -o models\image_segmentation_efficientsam_ti_2025april.onnx https://huggingface.co/opencv/image_segmentation_efficientsam/resolve/1e791988b34b2098736003057da0f3e6bc826259/image_segmentation_efficientsam_ti_2025april.onnx
if not exist models\object_detection_yolox_2022nov.onnx curl -fSL -o models\object_detection_yolox_2022nov.onnx https://huggingface.co/opencv/object_detection_yolox/resolve/78c368f74ce73ee28fc7a1be418a598c71b58b52/object_detection_yolox_2022nov.onnx
if not exist models\bioclip_image_int8.onnx curl -fSL -o models\bioclip_image_int8.onnx https://huggingface.co/Virien/naturdex-bioclip-onnx/resolve/fa3c062ea31a6e1881b1977fe555b2d481dca730/bioclip-image-int8.onnx
set BIO_DEMO=https://huggingface.co/spaces/imageomics/bioclip-demo/resolve/eeb91af989f1dffc405230a50b4c6214834c918b
if not exist models\bioclip_species_int8.npy (
    curl -fSL -o models\txt_emb_species.npy %BIO_DEMO%/txt_emb_species.npy
    curl -fSL -o models\txt_emb_species.json %BIO_DEMO%/txt_emb_species.json
    python -m app.services.species prepare models\txt_emb_species.npy models\txt_emb_species.json models
    del /q models\txt_emb_species.npy models\txt_emb_species.json
)

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
