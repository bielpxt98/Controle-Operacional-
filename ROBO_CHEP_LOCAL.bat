@echo off
title ROBO CHEP - PREENCHIMENTO AUTOMATICO
color 0A
cd /d "%~dp0"

echo ======================================================================
echo           ROBO CHEP - ATIVADOR DE PREENCHIMENTO AUTOMATICO
echo ======================================================================
echo  Conectando ao Supabase e preenchendo o portal CHEP...
echo ======================================================================
echo.

:: 1. Verifica se o Node.js esta instalado
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ALERTA] O Node.js nao foi detectado no sistema!
    echo.
    echo Se voce estiver no PC de casa pela primeira vez:
    echo 1. Va na pasta "instaladores" e execute o instalador do Node.js
    echo    ou baixe em: https://nodejs.org
    echo 2. Apos instalar, reinicie o computador ou abra este arquivo novamente.
    echo.
    pause
    exit /b 1
)

:: 2. Verifica se a pasta de modulos existe
if not exist "whatsapp-bot\node_modules" (
    echo [PRIMEIRA EXECUCAO] Instalando dependencias do robo, aguarde...
    cd whatsapp-bot
    call npm install
    cd ..
    echo [OK] Dependencias instaladas com sucesso!
    echo.
)

:: 3. Verifica se o navegador Chromium do Playwright existe
dir "%LOCALAPPDATA%\ms-playwright\chromium*" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [PRIMEIRA EXECUCAO] Baixando o navegador Chromium do Playwright...
    cd whatsapp-bot
    call npx playwright install chromium
    cd ..
    echo [OK] Navegador instalado com sucesso!
    echo.
)

:: 4. Executa o preenchimento das coletas no site da CHEP
echo [1/2] Consultando coletas pendentes no Supabase...
echo [2/2] Abrindo portal CHEP e preenchendo as programacoes...
echo.
node "whatsapp-bot\chep.js"

echo.
echo ======================================================================
echo  Execucao finalizada!
echo ======================================================================
pause
