@echo off
title OmniRoute (opsiyonel - normalde gerek yok)
echo [Youtube Asistani] NOT: start_hidden.vbs artik OmniRoute'u KENDISI de
echo penceresiz/otomatik baslatiyor. Bu dosyayi SADECE OmniRoute'u elle,
echo goz onunde (hata olursa gormek icin) baslatmak isterseniz kullanin.
echo.
echo OmniRoute baslatiliyor...
echo.

where omniroute >nul 2>nul
if %errorlevel% neq 0 (
    echo HATA: "omniroute" komutu bulunamadi ^(PATH'te yok^).
    echo Backend yine calisir ama Groq/OpenRouter yedeklerine dusecek.
    echo.
    pause
    exit /b 1
)

REM Zaten calisiyorsa TEKRAR baslatma (ust uste birden fazla OmniRoute
REM sureci birikmesin diye).
powershell -NoProfile -Command "exit [int](-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 20128 -WarningAction SilentlyContinue -InformationLevel Quiet))" >nul 2>nul
if %errorlevel% equ 0 (
    echo OmniRoute zaten calisiyor ^(:20128^), tekrar baslatilmadi.
    echo.
    pause
    exit /b 0
)

REM ONEMLI: "omniroute serve --daemon" dogrudan cagrilirsa arka plana
REM gecerken bazen KENDI konsolunu kapatirken bu pencereyi de beraberinde
REM kapatiyor (gozlemlenmis bir OmniRoute hatasi). "start" ile ayri/izole
REM bir pencerede baslatilinca bu pencere etkilenmiyor.
start "OmniRoute" /MIN omniroute serve --daemon --no-open

echo.
echo ------------------------------------------------------------
echo OmniRoute arka planda baslatildi (bu pencereyi kapatabilirsiniz).
echo Yukarida bir hata goruyorsaniz OmniRoute baslamamis olabilir --
echo backend yine de calisir, sadece Groq/OpenRouter yedeklerini kullanir.
echo ------------------------------------------------------------
pause
