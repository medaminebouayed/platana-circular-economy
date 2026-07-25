@echo off
chcp 65001 >nul
title Platana - Telechargement MVTec AD 1.3
color 0B

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║  PLATANA - Telechargement MVTec AD 1.3                     ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

set "PROJECT_ROOT=%CD%\platana-circular-economy"
set "MVTEC_DIR=%PROJECT_ROOT%\data\external\mvtec_ad"
set "MVTEC_URL=https://www.mydrive.ch/shares/150996/b52ecdcbf521176e9db9c731f2304b27/download/420938113-1629960298/mvtec_anomaly_detection.tar.xz"

if not exist "%PROJECT_ROOT%" (
    echo [ERREUR] Executer d'abord setup_1.1_structure.bat
    pause
    exit /b 1
)

if exist "%MVTEC_DIR%\bottle" (
    echo [INFO] MVTec deja present.
    choice /C ON /M "Re-telecharger ?"
    if !errorlevel! equ 2 goto :fin
    rmdir /S /Q "%MVTEC_DIR%" 2>nul
)

mkdir "%MVTEC_DIR%" 2>nul
set "MVTEC_ARCHIVE=%MVTEC_DIR%\mvtec.tar.xz"

echo [1/3] Telechargement...
powershell -Command "Invoke-WebRequest -Uri '%MVTEC_URL%' -OutFile '%MVTEC_ARCHIVE%' -TimeoutSec 600"

if not exist "%MVTEC_ARCHIVE%" (
    echo [ERREUR] Telechargement echoue
    pause
    exit /b 1
)
echo   [OK] Fichier telecharge

echo.
echo [2/3] Extraction...
tar -xf "%MVTEC_ARCHIVE%" -C "%MVTEC_DIR%"
if %errorlevel% neq 0 (
    echo [ERREUR] Extraction echouee. Installez 7-Zip.
    pause
    exit /b 1
)
echo   [OK] Extraction terminee

echo.
echo [3/3] Nettoyage...
del "%MVTEC_ARCHIVE%" 2>nul
echo   [OK] Archive supprimee

:: Verifier
set "COUNT=0"
for %%C in (bottle cable capsule carpet grid hazelnut leather metal_nut pill screw tile toothbrush transistor wood zipper) do (
    if exist "%MVTEC_DIR%\%%C" set /a COUNT+=1
)

echo.
echo [VERIFICATION] Categories: %COUNT%/15

:: Info JSON
(
echo {"dataset":"MVTec AD","categories":%COUNT%,"usage":"Pre-entrainement backbone","note":"Dataset mono-vue. Utilise pour apprendre les features de defauts visuels."}
) > "%MVTEC_DIR%\info.json"
echo   [OK] info.json cree

:fin
echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║  MVTec AD INSTALLE!                                          ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
echo Prochaine etape: Pre-entrainer le backbone
echo   python scripts\pretrain_backbone.py
echo.
pause
exit /b 0