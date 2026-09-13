@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Assistente Juridico
cd /d "%~dp0"
set "LOG=%~dp0iniciar_log.txt"

echo ========================================
echo   ASSISTENTE JURIDICO
echo ========================================
echo.
echo Pasta: %CD%
echo.
echo NAO use "Executar como administrador".
echo Dois cliques normais bastam.
echo Deixe esta janela ABERTA enquanto usar.
echo.

echo ==== INICIO %DATE% %TIME% ==== > "%LOG%"
echo Pasta=%CD% >> "%LOG%"

if not exist "app.py" (
  echo [ERRO] Voce precisa EXTRAIR o zip primeiro.
  echo Botao direito no zip ^> Extrair tudo
  echo Depois abra a pasta e rode Iniciar.bat la dentro.
  echo FALTA app.py >> "%LOG%"
  goto :erro
)

set "PYEXE="

REM 1) py launcher
where py >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
)

REM 2) python no PATH (ignora stub da Microsoft Store)
if not defined PYEXE (
  where python >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%I in ('where python 2^>nul') do (
      echo %%I | findstr /i "WindowsApps\\python.exe" >nul
      if errorlevel 1 if not defined PYEXE set "PYEXE=%%I"
    )
  )
)

REM 3) pastas comuns
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python310\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python310\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python311\python.exe" set "PYEXE=%ProgramFiles%\Python311\python.exe"

if not defined PYEXE (
  echo [ERRO] Python nao encontrado neste PC.
  echo.
  echo Faca assim:
  echo  1. Abra https://www.python.org/downloads/
  echo  2. Instale marcando: Add python.exe to PATH
  echo  3. Feche TUDO e rode Iniciar.bat de novo
  echo.
  start "" "https://www.python.org/downloads/"
  echo Python nao encontrado >> "%LOG%"
  goto :erro
)

echo Python OK:
echo   %PYEXE%
echo PYEXE=%PYEXE% >> "%LOG%"
"%PYEXE%" --version
"%PYEXE%" --version >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao executa.
  goto :erro
)
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual ^(primeira vez^)...
  if exist ".venv" rd /s /q ".venv" 2>nul
  "%PYEXE%" -m venv .venv >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo [ERRO] Nao criou .venv
    echo Extraia o zip na Area de Trabalho ^(fora do OneDrive se der erro^).
    echo venv falhou >> "%LOG%"
    goto :erro
  )
)

set "VPY=%CD%\.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [ERRO] .venv quebrado
  goto :erro
)

echo Instalando pacotes ^(pode demorar 1-2 min^)...
"%VPY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
"%VPY%" -m pip install -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERRO] Falha no pip. Veja iniciar_log.txt
  echo Precisa de internet. Antivirus pode bloquear.
  echo pip falhou >> "%LOG%"
  goto :erro
)

echo.
echo ========================================
echo   Abrindo http://127.0.0.1:8765
echo ========================================
echo.
echo Depois no site:
echo   Ajustes ^> Groq gratuito ^> cole chave gsk_...
echo   Chave: https://console.groq.com/keys
echo.
echo Se o Chrome nao abrir sozinho, cole a URL acima.
echo.

start "" http://127.0.0.1:8765
echo subindo app >> "%LOG%"
"%VPY%" app.py
set ERR=%ERRORLEVEL%
echo app saiu %ERR% >> "%LOG%"

echo.
if not "%ERR%"=="0" (
  echo [ERRO] O programa parou ^(codigo %ERR%^).
  echo - Porta 8765 ocupada? Feche outra janela do Assistente.
  echo - Ou reinicie o PC e tente de novo.
  goto :erro
)

echo Programa encerrado normalmente.
goto :fim

:erro
echo.
echo ---------- DEU ERRO ----------
echo Mande no WhatsApp:
echo   1^) print DESTA tela
echo   2^) o arquivo iniciar_log.txt ^(nesta pasta^)
echo   3^) ou rode Diagnostico.bat e mande diagnostico.txt
echo.
pause
exit /b 1

:fim
echo.
pause
exit /b 0
