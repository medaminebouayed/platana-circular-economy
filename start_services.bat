@echo off
TITLE Platana — Microservices Stack Launcher
echo.
echo =====================================================
echo     PLATANA CIRCULAR ECONOMY — Services Launcher
echo =====================================================
echo.

REM Check if Python venv exists
if not exist venv\Scripts\activate (
    echo [ERROR] Virtual environment not found. Run: python -m venv venv ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

echo [1/6] Starting Dify Stack (Docker)...
start "Dify Docker Stack" /min cmd /c "cd /d C:\Users\amine\OneDrive\Desktop\dify-main\docker && docker compose up -d"

timeout /t 3 /nobreak >nul

echo [2/6] Launching CV Service         (port 8001)...
start "CV Service" /D "%CD%" cmd /k venv\Scripts\python.exe -m uvicorn api.cv_service.main:app --host 0.0.0.0 --port 8001 --reload

timeout /t 1 /nobreak >nul

echo [3/6] Launching Pricing Service    (port 8002)...
start "Pricing Service" /D "%CD%" cmd /k venv\Scripts\python.exe -m uvicorn api.pricing_service.main:app --host 0.0.0.0 --port 8002 --reload

timeout /t 1 /nobreak >nul

echo [4/6] Launching Orchestrator       (port 8000)...
start "Orchestrator" /D "%CD%" cmd /k venv\Scripts\python.exe -m uvicorn api.orchestrator.main:app --host 0.0.0.0 --port 8000 --reload

timeout /t 1 /nobreak >nul

echo [5/6] Launching Main Service       (port 8003)...
start "Main Service" /D "%CD%" cmd /k venv\Scripts\python.exe -m uvicorn api.main_service.main:app --host 0.0.0.0 --port 8003 --reload

timeout /t 1 /nobreak >nul

echo [6/6] Launching Angular Frontend   (port 4200)...
start "Angular Frontend" /D "%CD%\frontend" cmd /k npm start

echo.
echo =====================================================
echo     All services launched successfully!
echo.
echo     Dify Console    : http://localhost
echo     CV Service      : http://localhost:8001/docs
echo     Pricing Service : http://localhost:8002/docs
echo     Orchestrator    : http://localhost:8000/docs
echo     Main Service    : http://localhost:8003/docs
echo.
echo     Frontend        : http://localhost:4200
echo =====================================================
echo.
pause
