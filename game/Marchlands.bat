@echo off
rem  Marchlands, without building anything.
rem
rem  Double-click this if you have Python and would rather not wait for a
rem  packaged build. It finds an interpreter, starts the game in your
rem  browser, and says something useful if it cannot.
setlocal
cd /d "%~dp0"

set PY=
where py >nul 2>&1 && set PY=py -3
if not defined PY (where python >nul 2>&1 && set PY=python)
if not defined PY (
  echo.
  echo   Marchlands needs Python 3.9 or newer, and this PC does not have it.
  echo   Get it from https://www.python.org/downloads/ ^(tick "Add to PATH"^),
  echo   or download Marchlands.exe from the Releases page instead.
  echo.
  pause
  exit /b 1
)

%PY% -m marchlands --web %*
if errorlevel 1 (
  echo.
  echo   Marchlands stopped with an error. If the port is busy, try:
  echo       Marchlands.bat --port 9000
  echo.
  pause
)
