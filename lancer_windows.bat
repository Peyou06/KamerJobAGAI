@echo off
echo 🇨🇲 Demarrage de CamerJob Watch...
echo.

REM Verifier Python
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo Erreur: Python non trouve. Installez Python 3.8+ depuis python.org
    pause
    exit
)

REM Installer dependances
pip install flask openpyxl

REM Trouver IP locale
for /f "tokens=*" %%a in ('python -c "import socket; s=socket.socket(); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()"') do set LOCAL_IP=%%a

echo.
echo Application demarree !
echo   Local     : http://localhost:5000
echo   Reseau LAN: http://%LOCAL_IP%:5000
echo.
echo Partagez l'adresse LAN avec votre equipe.
echo.

python app.py
pause
