@echo off
rem Arca - zero-setup launcher (Windows)
rem Double-click: start.bat
setlocal
cd /d "%~dp0"
echo ===^> Arca

rem 1) Locate Python 3.10+
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  echo Python 3.10+ is required but was not found.
  pause
  exit /b 1
)

rem 2) Create the virtual environment once
if not exist ".venv" (
  echo ===^> Creating virtual environment
  %PY% -m venv .venv
)
call .venv\Scripts\activate.bat

rem 3) Install Python dependencies
python -m pip install --quiet --disable-pip-version-check -r requirements.txt

rem 4) Build the frontend when Node.js is available and the bundle is stale
where node >nul 2>nul
if errorlevel 1 goto :checkfrontend
where npm >nul 2>nul
if errorlevel 1 goto :checkfrontend
pushd ui\web
set "NEED_BUILD="
for /f "delims=" %%F in ('powershell -NoProfile -Command "$d=Get-Item 'dist\index.html' -ErrorAction SilentlyContinue; if(-not $d -or (Get-ChildItem -Path src,index.html,package.json -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt $d.LastWriteTime } | Select-Object -First 1)) { 'yes' }"') do set "NEED_BUILD=%%F"
if "%NEED_BUILD%"=="yes" (
  echo ===^> Building frontend
  call npm install --no-audit --no-fund --silent
  call npm run build
)
popd
goto :startapp

:checkfrontend
if not exist "ui\web\dist\index.html" (
  echo WARNING: Node.js not found and no prebuilt frontend exists.
  echo The UI will not load. Install Node.js or build ui/web manually.
)

:startapp
echo ===^> Starting Arca
python run.py
endlocal
