@echo off
REM YouTube Assistant Setup + Uninstall sihirbazlarini tek dosyalik .exe'lere
REM paketler (ikisi de uzantinin kendi simgesiyle). Cikti:
REM   installer\dist\YouTubeAssistantSetup.exe
REM   installer\dist\YouTubeAssistantUninstall.exe
REM Ikisini de GitHub Releases'e yukleyin.

cd /d "%~dp0"

python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo PyInstaller kurulamadi. Python ve pip kurulu oldugundan emin olun.
    exit /b 1
)

python -m PyInstaller --onefile --windowed --icon=assets\app.ico --name YouTubeAssistantSetup setup_wizard.py
python -m PyInstaller --onefile --windowed --icon=assets\app.ico --name YouTubeAssistantUninstall uninstall_wizard.py

echo.
echo Bitti:
echo   installer\dist\YouTubeAssistantSetup.exe
echo   installer\dist\YouTubeAssistantUninstall.exe
pause
