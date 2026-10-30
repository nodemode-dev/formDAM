@echo off
REM Builds the formDAM Windows desktop app: the Tauri shell over the engine frozen with PyInstaller (onedir, bundled as a
REM resource), packaged as NSIS and MSI installers. Run it on Windows from anywhere: setup\build_windows_app.bat
REM It mirrors build_linux_app step for step; BUNDLES=nsis or BUNDLES=msi builds one installer only.
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"
if not defined BUNDLES set "BUNDLES=nsis,msi"

echo.
echo == Checking prerequisites ==
where python >nul 2>nul || ( echo python is required: https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) & exit /b 1 )
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || ( echo Python 3.10 or newer is required & exit /b 1 )
where npm >nul 2>nul || ( echo npm is required: https://nodejs.org & exit /b 1 )
node -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit(a>22||(a===22&&b>=12)||(a===20&&b>=19)?0:1)" || ( echo Node 20.19 or 22.12 or newer is required: https://nodejs.org & exit /b 1 )
where cargo >nul 2>nul || ( echo Rust is required: https://rustup.rs ^(with the Visual Studio C++ build tools it offers^) & exit /b 1 )

echo.
echo == Fetching face and visual search models (sha256-verified) ==
if not exist backend\models mkdir backend\models
set "FETCH=python "%ROOT%\setup\fetch_model.py" backend\models"
%FETCH% face_detection_yunet_2023mar.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx 8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4 || goto :nonet
%FETCH% face_recognition_sface_2021dec.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx 0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79 || goto :nonet
set "CLIP_BASE=https://huggingface.co/onnx-community/CLIP-ViT-B-32-laion2B-s34B-b79K-ONNX/resolve/de693d0"
%FETCH% clip_vit_b32_laion2b_int8.onnx %CLIP_BASE%/onnx/model_quantized.onnx 2ac8410fe198fbd003cd97460bdd68653d99c33f53311881cd306190067aee9b || goto :nonet
%FETCH% clip_vocab.json %CLIP_BASE%/vocab.json 5047b556ce86ccaf6aa22b3ffccfc52d391ea4accdab9c2f2407da5b742d4363 || goto :nonet
%FETCH% clip_merges.txt %CLIP_BASE%/merges.txt 9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a || goto :nonet
%FETCH% inpainting_lama_2025jan.onnx https://huggingface.co/opencv/inpainting_lama/resolve/aee6d22f0a13e5e35af1c9a1c3afd62841fc6f3f/inpainting_lama_2025jan.onnx 7df918ac3921d3daf0aae1d219776cf0dc4e4935f035af81841b40adcf74fdf2 || goto :nonet
%FETCH% image_segmentation_efficientsam_ti_2025april.onnx https://huggingface.co/opencv/image_segmentation_efficientsam/resolve/1e791988b34b2098736003057da0f3e6bc826259/image_segmentation_efficientsam_ti_2025april.onnx 4eb496e0a7259d435b49b66faf1754aa45a5c382a34558ddda9a8c6fe5915d77 || goto :nonet
%FETCH% object_detection_yolox_2022nov.onnx https://huggingface.co/opencv/object_detection_yolox/resolve/78c368f74ce73ee28fc7a1be418a598c71b58b52/object_detection_yolox_2022nov.onnx c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063 || goto :nonet
%FETCH% bioclip_image_int8.onnx https://huggingface.co/Virien/naturdex-bioclip-onnx/resolve/fa3c062ea31a6e1881b1977fe555b2d481dca730/bioclip-image-int8.onnx ae858e6a807b3a19d1e1f9ecbe3cc5302badf0a6a0cddcc5d1728cdf9d28517a || goto :nonet
set "BIO_DEMO=https://huggingface.co/spaces/imageomics/bioclip-demo/resolve/eeb91af989f1dffc405230a50b4c6214834c918b"
if exist backend\models\bioclip_species_int8.npy goto :models_done
%FETCH% txt_emb_species.npy %BIO_DEMO%/txt_emb_species.npy 91ce02dff2433222e3138b8bf7eefa1dd74b30f4d406c16cd3301f66d65ab4ed || goto :nonet
%FETCH% txt_emb_species.json %BIO_DEMO%/txt_emb_species.json 844e6fabc06cac072214d566b78f40825b154efa9479eb11285030ca038b2ece || goto :nonet
:models_done

echo.
echo == Building the frontend ==
cd /d "%ROOT%\frontend"
if not exist node_modules ( call npm install || exit /b 1 )
call npm run build || exit /b 1

echo.
echo == Building the engine (Python -^> one folder) ==
cd /d "%ROOT%\backend"
if exist .venv-package rmdir /s /q .venv-package
python -m venv .venv-package || exit /b 1
call .venv-package\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller==6.16.0 || exit /b 1
if exist models\bioclip_species_int8.npy goto :species_done
python -m app.services.species prepare models\txt_emb_species.npy models\txt_emb_species.json models || exit /b 1
del /q models\txt_emb_species.npy models\txt_emb_species.json
:species_done
pyinstaller --clean --noconfirm --onedir --name formdam-backend ^
  --collect-all uvicorn --collect-all PIL --collect-all pi_heif --exclude-module pillow_heif ^
  --collect-all cv2 --collect-all numpy --collect-all rawpy --collect-all exifread ^
  --collect-all onnxruntime --collect-all cryptography ^
  --hidden-import app.familyserver --collect-all pyzipper --collect-all Cryptodome ^
  --exclude-module pymobiledevice3 ^
  --hidden-import app.main ^
  --add-data "..\frontend\dist;frontend_dist" ^
  --add-data "models;models" ^
  --add-data "app\data;app\data" ^
  --add-data "..\frontend\package.json;." ^
  desktop_entry.py || exit /b 1
dist\formdam-backend\formdam-backend.exe --selfcheck || exit /b 1
call deactivate

echo.
echo == Placing the engine tree (onedir: no per-launch extraction, fast cold start) ==
cd /d "%ROOT%"
if exist src-tauri\binaries\formdam-backend rmdir /s /q src-tauri\binaries\formdam-backend
xcopy /e /i /q /y backend\dist\formdam-backend src-tauri\binaries\formdam-backend >nul || exit /b 1
echo engine: src-tauri\binaries\formdam-backend\ (bundled via resources)

if not exist src-tauri\icons\icon.icns copy /y src-tauri\icons\source\icon.icns src-tauri\icons\icon.icns >nul
if exist src-tauri\icons\icon.ico goto :icon_done
echo.
echo == Generating the Windows icon from src-tauri\icons\icon.png ==
set "ICONTMP=%TEMP%\formdam-icons-%RANDOM%"
call npx --yes @tauri-apps/cli@2.12.3 icon src-tauri\icons\icon.png -o "%ICONTMP%" || exit /b 1
copy /y "%ICONTMP%\icon.ico" src-tauri\icons\icon.ico >nul || exit /b 1
rmdir /s /q "%ICONTMP%"
:icon_done

echo.
echo == Building the app bundle (this compiles Rust; first run takes a while) ==
cd /d "%ROOT%\src-tauri"
call npx --yes @tauri-apps/cli@2.12.3 build --bundles %BUNDLES% -- --locked || exit /b 1
cd /d "%ROOT%"

echo.
echo == Done ==
for %%F in ("src-tauri\target\release\bundle\nsis\*.exe" "src-tauri\target\release\bundle\msi\*.msi") do if exist "%%~F" echo Installer: %%~fF
echo ffmpeg stays a user-supplied PATH binary (video features need it): winget install Gyan.FFmpeg
exit /b 0

:nonet
echo could not download a model (network or DNS); nothing else changed, rerun setup\build_windows_app.bat when the connection is back
exit /b 1
