@echo off
chcp 65001 >nul
title Assistente Juridico - Diagnostico
cd /d "%~dp0"
set "LOG=%~dp0diagnostico.txt"

echo Diagnostico Assistente Juridico > "%LOG%"
echo Data: %DATE% %TIME% >> "%LOG%"
echo Pasta: %CD% >> "%LOG%"
echo. >> "%LOG%"

echo === Arquivos === >> "%LOG%"
if exist "app.py" (echo OK app.py >> "%LOG%") else (echo FALTA app.py >> "%LOG%")
if exist "requirements.txt" (echo OK requirements.txt >> "%LOG%") else (echo FALTA requirements.txt >> "%LOG%")
if exist "Iniciar.bat" (echo OK Iniciar.bat >> "%LOG%") else (echo FALTA Iniciar.bat >> "%LOG%")
echo. >> "%LOG%"

echo === Python no PATH === >> "%LOG%"
where py >> "%LOG%" 2>&1
where python >> "%LOG%" 2>&1
where python3 >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo === Versoes === >> "%LOG%"
py -3 --version >> "%LOG%" 2>&1
python --version >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo === Locais comuns === >> "%LOG%"
if exist "%LocalAppData%\Programs\Python" dir /b "%LocalAppData%\Programs\Python" >> "%LOG%" 2>&1
if exist "%ProgramFiles%\Python*" dir /b "%ProgramFiles%\Python*" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo === Porta 8765 === >> "%LOG%"
netstat -ano | findstr ":8765" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo === .venv === >> "%LOG%"
if exist ".venv\Scripts\python.exe" (
  echo OK .venv >> "%LOG%"
  ".venv\Scripts\python.exe" --version >> "%LOG%" 2>&1
) else (
  echo SEM .venv ainda >> "%LOG%"
)

echo.
echo Pronto. Arquivo gerado:
echo %LOG%
echo.
echo Envie este arquivo diagnostico.txt no WhatsApp.
echo.
notepad "%LOG%"
pause
