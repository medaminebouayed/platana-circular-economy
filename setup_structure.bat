@echo off
chcp 65001 >nul
title Platana - Setup Structure 1.1
color 0A

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║  PLATANA - Projet 3: Circular Economy Intelligence           ║
echo ║  Etape 1.1: Creation de la structure du projet              ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

set "PROJECT_ROOT=%CD%\platana-circular-economy"
echo [INFO] Repertoire racine: %PROJECT_ROOT%
echo.

:: Dossiers principaux
echo [1/6] Creation des dossiers principaux...
if not exist "%PROJECT_ROOT%" mkdir "%PROJECT_ROOT%"
cd /d "%PROJECT_ROOT%"

:: Data
call :create_dir "data\raw" "donnees brutes"
call :create_dir "data\processed" "donnees pretraitees"
call :create_dir "data\processed\train" "donnees d'entrainement"
call :create_dir "data\processed\val" "donnees de validation"
call :create_dir "data\external" "datasets externes"
call :create_dir "data\annotations" "fichiers d'annotation"

:: Models
call :create_dir "models\cv" "modeles CV"
call :create_dir "models\cv\checkpoints" "checkpoints CV"
call :create_dir "models\pricing" "modeles pricing"
call :create_dir "models\pricing\checkpoints" "checkpoints pricing"

:: API
call :create_dir "api\shared" "modules partages"
call :create_dir "api\cv_service" "API CV"
call :create_dir "api\pricing_service" "API Pricing"
call :create_dir "api\orchestrator" "API Orchestrateur"

:: Autres
call :create_dir "configs" "configurations"
call :create_dir "scripts" "scripts utilitaires"
call :create_dir "notebooks" "Jupyter notebooks"
call :create_dir "tests" "tests"
call :create_dir "workflows\dify" "workflows Dify"
call :create_dir "docs" "documentation"

:: Fichiers de base
echo.
echo [2/6] Creation des fichiers de base...

(
echo # Python
echo __pycache__/
echo *.py[cod]
echo *$py.class
echo *.so
echo .Python
echo venv/
echo env/
echo .env
echo.
echo # Data
echo data/raw/*
echo data/processed/*
echo data/external/*
echo !data/**/.gitkeep
echo.
echo # Models
echo *.pt
echo *.pth
echo *.onnx
echo models/**/checkpoints/*
echo !models/**/checkpoints/.gitkeep
echo.
echo # MLflow
echo mlruns/
echo.
echo # IDE
echo .vscode/
echo .idea/
echo.
echo # OS
echo .DS_Store
echo Thumbs.db
) > "%PROJECT_ROOT%\.gitignore"
echo   [OK] .gitignore

:: Fichiers .gitkeep
type nul > "%PROJECT_ROOT%\data\raw\.gitkeep"
type nul > "%PROJECT_ROOT%\data\processed\.gitkeep"
type nul > "%PROJECT_ROOT%\data\external\.gitkeep"
type nul > "%PROJECT_ROOT%\models\cv\checkpoints\.gitkeep"
type nul > "%PROJECT_ROOT%\models\pricing\checkpoints\.gitkeep"
echo   [OK] Fichiers .gitkeep

:: README.md
(
echo # Platana - Circular Economy Intelligence
echo.
echo ## Projet 3: Refurbishment ^& Resale Engine
echo.
echo ### Architecture
echo ```text
echo [Photos] → [CV Grading] → [Decision] → [Pricing] → [Dify Fiche] → [Publication]
echo ```
echo.
echo ### Structure
echo - `data/` - Donnees
echo - `models/` - Modeles ML
echo - `api/` - Microservices
echo - `configs/` - Configurations
echo - `scripts/` - Scripts
echo.
echo ### Demarrage
echo 1. `setup_1.1_structure.bat`
echo 2. `setup_1.2_env.bat`
echo 3. `setup_1.3_download_mvtec.bat`
) > "%PROJECT_ROOT%\README.md"
echo   [OK] README.md

:: .env.template
(
echo # API Keys
echo OPENAI_API_KEY=your-key-here
echo ANTHROPIC_API_KEY=your-key-here
echo DIFY_API_KEY=your-key-here
echo.
echo # Services
echo CV_SERVICE_PORT=8001
echo PRICING_SERVICE_PORT=8002
echo ORCHESTRATOR_PORT=8000
echo.
echo # Database
echo DATABASE_URL=postgresql://user:pass@localhost:5432/platana
echo.
echo # MLflow
echo MLFLOW_TRACKING_URI=http://localhost:5000
) > "%PROJECT_ROOT%\.env.template"
echo   [OK] .env.template

:: activate.bat
(
@echo off
echo cd /d "%PROJECT_ROOT%"
echo call venv\Scripts\activate.bat
echo echo [OK] Environnement active!
) > "%PROJECT_ROOT%\activate.bat"
echo   [OK] activate.bat

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║  STRUCTURE CREE AVEC SUCCES                                  ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
tree /F "%PROJECT_ROOT%" | findstr /V ".gitkeep"
echo.
pause
exit /b 0

:create_dir
if not exist "%~1" (
    mkdir "%~1"
    echo   [OK] %~1
) else (
    echo   [EXISTS] %~1
)
exit /b 0