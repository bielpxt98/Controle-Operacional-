@echo off
title CRIAR ATALHO COM ICONE PURM
color 0A
cd /d "%~dp0"

echo Criando atalho na sua Area de Trabalho com o icone da PURM...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $d = [Environment]::GetFolderPath('Desktop'); $curr = (Get-Location).Path; $s = $ws.CreateShortcut(\"$d\ROBO CHEP.lnk\"); if (Test-Path \"$curr\CLIQUE_AQUI_PARA_RODAR_ROBO.bat\") { $s.TargetPath = \"$curr\CLIQUE_AQUI_PARA_RODAR_ROBO.bat\"; } else { $s.TargetPath = \"$curr\ROBO_CHEP_LOCAL.bat\"; } $s.WorkingDirectory = \"$curr\"; if (Test-Path \"$curr\purm_logo.ico\") { $s.IconLocation = \"$curr\purm_logo.ico,0\"; } elseif (Test-Path \"$curr\assets\purm_logo.ico\") { $s.IconLocation = \"$curr\assets\purm_logo.ico,0\"; } $s.Description = 'Robo CHEP - PURM Transportes'; $s.Save()"

echo.
echo ======================================================================
echo  Atalho 'ROBO CHEP' com o icone PURM criado na sua Area de Trabalho!
echo ======================================================================
echo.
pause
