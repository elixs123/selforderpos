@echo off
cd /d %~dp0
echo Instaliram Microsoft Visual C++ (potrebno za Qt)...
if exist vc_redist.x64.exe vc_redist.x64.exe /install /quiet /norestart
if not exist .env (
    copy /y .env.primjer .env >nul
    echo Napravljen .env - upisi postavke kase u njega.
    notepad .env
)
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Kasa.lnk');$s.TargetPath='%~dp0Kasa.exe';$s.WorkingDirectory='%~dp0';$s.Save()"
echo Pokrecem kasu...
start "" "%~dp0Kasa.exe"
timeout /t 8 >nul
if exist kasa.log (
    echo.
    echo ---- zadnji redovi kasa.log ----
    powershell -NoProfile -Command "Get-Content kasa.log -Tail 25"
)
pause
