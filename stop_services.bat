@echo off
TITLE Stopping Microservices & Dify Stack
echo.
echo =====================================================
echo     PLATANA CIRCULAR ECONOMY — Services Stopper
echo =====================================================
echo.

echo [1/2] Terminating processes listening on ports 8000, 8001, 8002, 8003, and 4200...

for %%p in (8000 8001 8002 8003 4200) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r /c:":%%p[ ]*LISTENING"') do (
        echo Killing process tree on PID %%a (Port %%p)...
        taskkill /F /T /PID %%a 2>nul
    )
)

echo.
echo [2/2] Stopping Dify Stack (Docker)...
pushd C:\Users\amine\OneDrive\Desktop\dify-main\docker
docker compose down
popd

echo.
echo =====================================================
echo     All microservices, Angular, and Dify stopped!
echo =====================================================
echo.
pause