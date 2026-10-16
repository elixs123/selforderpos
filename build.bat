@echo off
cd /d %~dp0
if not exist .venv (
    py -3.12 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip uninstall -y PySide6 PySide6-Essentials PySide6-Addons shiboken6
pip install -r requirements.txt pyinstaller
if exist dist\Kasa rmdir /s /q dist\Kasa
pyinstaller --noconfirm --clean --windowed --name Kasa ^
    --paths cameras ^
    --add-data "assets;assets" ^
    --add-data "cameras\models;models" ^
    --hidden-import camera_service --hidden-import guard --hidden-import reader --hidden-import config ^
    --hidden-import embedder --hidden-import hands --hidden-import similarity --hidden-import samples ^
    --hidden-import watcher --hidden-import zones --hidden-import locations --hidden-import catalog ^
    --hidden-import pyodbc ^
    --collect-all mediapipe --collect-all onnxruntime ^
    app.py
if errorlevel 1 goto failed

set QTDIR=dist\Kasa\_internal\PySide6
for %%p in (msvcp*.dll vcruntime*.dll concrt*.dll) do (
    copy /y "%QTDIR%\%%p" "dist\Kasa\_internal\" >nul 2>nul
    copy /y "%QTDIR%\%%p" "%QTDIR%\plugins\platforms\" >nul 2>nul
)
if exist cameras\zones.json copy /y cameras\zones.json dist\Kasa\zones.json >nul
copy /y .env.example dist\Kasa\.env.primjer >nul
copy /y install_kasa.bat dist\Kasa\instaliraj.bat >nul
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing https://aka.ms/vs/17/release/vc_redist.x64.exe -OutFile dist\Kasa\vc_redist.x64.exe"

echo.
echo Gotovo: dist\Kasa
echo Kopiraj CIJELI folder dist\Kasa na kasu i tamo pokreni instaliraj.bat
pause
exit /b 0

:failed
echo.
echo PAKOVANJE NIJE USPJELO - posalji zadnje redove iznad
pause
exit /b 1
