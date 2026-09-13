@echo off
chcp 65001 >nul
title Assistente Juridico
cd /d "%~dp0"

echo ========================================
echo   ASSISTENTE JURIDICO
echo ========================================
echo.
echo Pasta: %CD%
echo.
echo NAO precisa executar como Administrador.
echo Deixe esta janela ABERTA enquanto usar.
echo Fechar esta janela = o site para de funcionar.
echo.

REM --- Checagem: extraiu o zip? ---
if not exist "app.py" (
  echo [ERRO] Nao achei app.py nesta pasta.
  echo Extraia o ZIP inteiro (botao direito ^> Extrair tudo)
  echo e rode o Iniciar.bat DE DENTRO da pasta extraida.
  echo.
  goto :fim_erro
)

REM --- Acha o Python (sem admin) ---
set "PYLAUNCH="
where py >nul 2>nul
if %errorlevel%==0 set "PYLAUNCH=py -3"
if not defined PYLAUNCH (
  where python >nul 2>nul
  if %errorlevel%==0 set "PYLAUNCH=python"
)
if not defined PYLAUNCH (
  echo [ERRO] Python nao encontrado.
  echo.
  echo 1) Baixe: https://www.python.org/downloads/
  echo 2) Na instalacao, MARQUE: "Add python.exe to PATH"
  echo 3) Feche e abra de novo esta janela / reinicie o PC
  echo 4) Rode Iniciar.bat de novo ^(clique normal, SEM administrador^)
  echo.
  goto :fim_erro
)

echo Usando: %PYLAUNCH%
%PYLAUNCH% --version
if errorlevel 1 (
  echo [ERRO] Python instalado, mas nao executa.
  goto :fim_erro
)
echo.

REM --- Ambiente virtual (pasta do usuario, sem admin) ---
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente .venv ^(primeira vez, pode demorar^)...
  if exist ".venv" rd /s /q ".venv" 2>nul
  %PYLAUNCH% -m venv .venv
  if errorlevel 1 (
    echo [ERRO] Falha ao criar .venv
    echo Tente extrair o zip para Documentos ou Area de Trabalho
    echo ^(evite pasta do OneDrive se der erro^).
    goto :fim_erro
  )
)

call "%~dp0.venv\Scripts\activate.bat"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ERRO] activate falhou.
  goto :fim_erro
)

echo Instalando dependencias ^(primeira vez demora 1-2 min^)...
python -m pip install -q --upgrade pip
if errorlevel 1 (
  echo [ERRO] pip nao funcionou. Verifique internet.
  goto :fim_erro
)
python -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [ERRO] Nao instalou os pacotes. Verifique internet / antivirus.
  goto :fim_erro
)

echo.
echo ========================================
echo   Abrindo http://127.0.0.1:8765
echo ========================================
echo.
echo Depois: Ajustes ^> Groq gratuito ^> cole a chave gsk_...
echo Chave: https://console.groq.com/keys
echo.
echo Se a tela nao abrir, cole no Chrome: http://127.0.0.1:8765
echo.

start "" "http://127.0.0.1:8765"
python app.py
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
  echo [ERRO] O programa parou ^(codigo %ERR%^).
  echo Se aparecer "Address already in use", ja tem uma
  echo janela aberta — use aquela, ou reinicie o PC.
  goto :fim_erro
)

echo Programa encerrado.
goto :fim

:fim_erro
echo.
echo ---------- DEU ERRO ----------
echo Tire um print desta tela e me envie.
echo.
pause
exit /b 1

:fim
echo.
echo Pressione qualquer tecla para fechar esta janela.
pause
exit /b 0
