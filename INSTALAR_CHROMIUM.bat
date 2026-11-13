@echo off
title INSTALADOR DO NAVEGADOR CHROMIUM - PLAYWRIGHT
color 0B
cd /d "%~dp0"

echo ======================================================================
echo       INSTALACAO DO NAVEGADOR CHROMIUM PARA O ROBO CHEP
echo ======================================================================
echo.
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERRO] O Node.js nao esta instalado. Instale o Node.js primeiro!
    pause
    exit /b 1
)

echo Baixando e configurando o Chromium (aguarde, isso e feito apenas 1 vez)...
cd whatsapp-bot
call npx playwright install chromium
cd ..

echo.
echo ======================================================================
echo  Chromium instalado e pronto para o robo CHEP!
echo ======================================================================
pause
