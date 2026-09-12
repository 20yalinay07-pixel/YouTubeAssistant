@echo off
REM Youtube Asistani - Backend Baslatici (GORUNUR pencere, debug icin)
REM Bu dosya SADECE backend'i baslatir; sunucu herhangi bir sebeple
REM kapanirsa (hata, coku vb.) 3 saniye sonra otomatik yeniden baslatir.
REM
REM OmniRoute ARTIK BURADAN baslatilmiyor -- ayri dosyaya tasindi:
REM once "start_omniroute.bat"'i calistirin (kendi penceresinde acilir,
REM hata olursa orada gorursunuz), SONRA bunu calistirin. OmniRoute
REM calismiyorsa da sorun degil, backend otomatik Groq/OpenRouter'a duser.
REM
REM Gunluk kullanim icin onerilen: start_hidden.vbs (tepsi ikonu, konsol
REM penceresi acmaz). Bu dosya, konsol ciktisini GORMEK isterken/debug
REM ederken kullanilir.

cd /d "%~dp0backend"

:calistir
echo [Youtube Asistani] Sunucu baslatiliyor...
python server.py
echo [Youtube Asistani] Sunucu durdu, 3 saniye icinde yeniden baslatilacak...
timeout /t 3 /nobreak >nul
goto calistir
