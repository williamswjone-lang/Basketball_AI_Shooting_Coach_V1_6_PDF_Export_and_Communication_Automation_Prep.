@echo off
setlocal

echo Starting Basketball AI Team Preview...

echo.
echo This starts Streamlit on 0.0.0.0 so teammates on the same network can open it.
echo For internet sharing, deploy with Render using render.yaml.
echo.

set "ENV_DIR="

if exist .venv311\Scripts\python.exe (
    set "ENV_DIR=.venv311"
) else if exist .venv\Scripts\python.exe (
    set "ENV_DIR=.venv"
) else if exist .venv313\Scripts\python.exe (
    set "ENV_DIR=.venv313"
) else (
    echo Creating .venv311 with Python 3.11...
    py -3.11 -m venv .venv311
    if errorlevel 1 (
        echo Python 3.11 launcher unavailable. Creating .venv with default Python...
        python -m venv .venv
        set "ENV_DIR=.venv"
    ) else (
        set "ENV_DIR=.venv311"
    )
)

echo Using environment: %ENV_DIR%
call %ENV_DIR%\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Starting app...
echo Local URL:   http://localhost:8501
echo LAN URL:     http://YOUR_COMPUTER_IP:8501
echo.

streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.fileWatcherType none

pause
endlocal
