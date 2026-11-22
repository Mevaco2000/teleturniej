@echo off
rem Uruchamia serwer gry. Przy pierwszym starcie przygotowuje srodowisko Pythona.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Nie znaleziono Pythona. Zainstaluj Pythona 3.11 lub nowszego z https://www.python.org/downloads/
  echo Podczas instalacji zaznacz opcje "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Przygotowuje srodowisko, to potrwa chwile...
  python -m venv .venv
  if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

".venv\Scripts\python.exe" -m server %*
pause
exit /b 0

:failed
echo Nie udalo sie przygotowac srodowiska. Sprawdz polaczenie z internetem i sprobuj ponownie.
pause
exit /b 1
