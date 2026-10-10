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
set "FETCH=python "%ROOT%\setup\fetch_model.py" models"
%FETCH% face_detection_yunet_2023mar.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx 8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4 || exit /b 1
%FETCH% face_recognition_sface_2021dec.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx 0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79 || exit /b 1
set CLIP_BASE=https://huggingface.co/onnx-community/CLIP-ViT-B-32-laion2B-s34B-b79K-ONNX/resolve/de693d0
%FETCH% clip_vit_b32_laion2b_int8.onnx %CLIP_BASE%/onnx/model_quantized.onnx 2ac8410fe198fbd003cd97460bdd68653d99c33f53311881cd306190067aee9b || exit /b 1
%FETCH% clip_vocab.json %CLIP_BASE%/vocab.json 5047b556ce86ccaf6aa22b3ffccfc52d391ea4accdab9c2f2407da5b742d4363 || exit /b 1
%FETCH% clip_merges.txt %CLIP_BASE%/merges.txt 9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a || exit /b 1
%FETCH% inpainting_lama_2025jan.onnx https://huggingface.co/opencv/inpainting_lama/resolve/aee6d22f0a13e5e35af1c9a1c3afd62841fc6f3f/inpainting_lama_2025jan.onnx 7df918ac3921d3daf0aae1d219776cf0dc4e4935f035af81841b40adcf74fdf2 || exit /b 1
%FETCH% image_segmentation_efficientsam_ti_2025april.onnx https://huggingface.co/opencv/image_segmentation_efficientsam/resolve/1e791988b34b2098736003057da0f3e6bc826259/image_segmentation_efficientsam_ti_2025april.onnx 4eb496e0a7259d435b49b66faf1754aa45a5c382a34558ddda9a8c6fe5915d77 || exit /b 1
%FETCH% object_detection_yolox_2022nov.onnx https://huggingface.co/opencv/object_detection_yolox/resolve/78c368f74ce73ee28fc7a1be418a598c71b58b52/object_detection_yolox_2022nov.onnx c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063 || exit /b 1
%FETCH% bioclip_image_int8.onnx https://huggingface.co/Virien/naturdex-bioclip-onnx/resolve/fa3c062ea31a6e1881b1977fe555b2d481dca730/bioclip-image-int8.onnx ae858e6a807b3a19d1e1f9ecbe3cc5302badf0a6a0cddcc5d1728cdf9d28517a || exit /b 1
set BIO_DEMO=https://huggingface.co/spaces/imageomics/bioclip-demo/resolve/eeb91af989f1dffc405230a50b4c6214834c918b
if not exist models\bioclip_species_int8.npy (
    %FETCH% txt_emb_species.npy %BIO_DEMO%/txt_emb_species.npy 91ce02dff2433222e3138b8bf7eefa1dd74b30f4d406c16cd3301f66d65ab4ed || exit /b 1
    %FETCH% txt_emb_species.json %BIO_DEMO%/txt_emb_species.json 844e6fabc06cac072214d566b78f40825b154efa9479eb11285030ca038b2ece || exit /b 1
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
