@echo off
REM YouTube Assistant - Kaldirma
REM Ne yapar: (1) Baslangic klasorundeki otomatik-baslatma kisayolunu siler,
REM (2) arka planda calisan tray_launcher.py / pot_server islemlerini durdurur.
REM Proje klasorunu ve .env icindeki anahtarlarinizi SILMEZ -- onlari isterseniz
REM elle silin, geri donusu olmayan bir islem otomatik yapilmiyor.

setlocal
title YouTube Assistant - Kaldirma

echo YouTube Assistant kaldiriliyor...
echo.

set "STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\YouTube Assistant.lnk"
if exist "%STARTUP_LNK%" (
    del /f /q "%STARTUP_LNK%"
    echo [OK] Baslangic kisayolu kaldirildi.
) else (
    echo [-] Baslangic kisayolu zaten yok.
)

echo Arka plan servisleri durduruluyor (varsa)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'tray_launcher\.py|pot_server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo [OK] Servisler durduruldu (calisiyorsa).

echo.
echo Tamamlandi. Proje klasorunu ve icindeki .env dosyanizi (API anahtarlariniz)
echo bu islem SILMEDI -- tamamen kaldirmak isterseniz bu klasoru elle silebilirsiniz.
echo.
pause
