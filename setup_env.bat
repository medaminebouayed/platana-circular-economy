@echo off
chcp 65001 >nul
title Platana - Setup Environnement 1.2
color 0E

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║  PLATANA - Setup Environnement Python 1.2                    ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

set "PROJECT_ROOT=%CD%\platana-circular-economy"
if not exist "%PROJECT_ROOT%" (
    echo [ERREUR] Executer d'abord setup_1.1_structure.bat
    pause
    exit /b 1
)

cd /d "%PROJECT_ROOT%"

:: Verifier Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python non installe
    pause
    exit /b 1
)

:: Creer venv
echo [1/4] Creation du venv...
if exist "venv" rmdir /S /Q "venv"
python -m venv venv
echo   [OK] venv cree

:: Creer requirements.txt
echo.
echo [2/4] Creation de requirements.txt...
(
echo timm^>=0.9.0
echo albumentations^>=1.3.0
echo opencv-python-headless^>=4.8.0
echo Pillow^>=10.0.0
echo numpy^>=1.24.0
echo xgboost^>=2.0.0
echo lightgbm^>=4.1.0
echo scikit-learn^>=1.3.0
echo pandas^>=2.0.0
echo fastapi^>=0.104.0
echo uvicorn[standard]^>=0.24.0
echo pydantic^>=2.5.0
echo sqlalchemy^>=2.0.0
echo python-multipart^>=0.0.6
echo mlflow^>=2.8.0
echo onnx^>=1.15.0
echo onnxruntime^>=1.16.0
echo ortools^>=9.8.0
echo prometheus-client^>=0.19.0
echo pytest^>=7.4.0
echo black^>=23.0.0
echo jupyter^>=1.0.0
echo matplotlib^>=3.8.0
echo seaborn^>=0.13.0
echo pyyaml^>=6.0.1
echo python-dotenv^>=1.0.0
echo requests^>=2.31.0
echo tqdm^>=4.66.0
echo httpx^>=0.25.0
) > "requirements.txt"
echo   [OK] requirements.txt

:: Installer PyTorch avec CUDA
echo.
echo [3/4] Installation de PyTorch (CUDA 12.8)...
echo   [INFO] Telechargement PyTorch avec support GPU (~2.8 Go)...
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

if %errorlevel% neq 0 (
    echo [ERREUR] Installation PyTorch echouee
    pause
    exit /b 1
)

:: Installer le reste
echo.
echo [4/4] Installation des dependances...
echo   [INFO] Cela peut prendre 10-15 minutes...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo [ERREUR] Installation echouee
    pause
    exit /b 1
)

pip freeze > "requirements.lock.txt"
echo   [OK] Installation terminee

:: Verifier
echo.
echo [VERIFICATION]
python -c "import torch; print('  [OK] PyTorch', torch.__version__, '- CUDA:', torch.cuda.is_available())"
python -c "import timm; print('  [OK] timm', timm.__version__)"
python -c "import fastapi; print('  [OK] FastAPI', fastapi.__version__)"

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║  ENVIRONNEMENT CONFIGURE!                                    ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
echo Prochaine etape: setup_1.3_download_mvtec.bat
echo.
pause
exit /b 0