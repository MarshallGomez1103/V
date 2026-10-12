@echo off
rem V. Double-click to open the app.
rem Python is not required: uv installs itself and fetches Python and the rest.
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo Installing uv, this only happens the first time...
  set UV_NO_MODIFY_PATH=1
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
)
echo Opening V. The first run downloads what it needs and takes a few minutes.
echo To close V, close this window or press Ctrl+C.
rem "voz" (not "v"): it exists in every environment, including an old .venv that
rem predates the "v" entry point; both start the same app. uv run syncs first.
uv run --extra asr-local --extra diarization voz %*
if errorlevel 1 (
  echo.
  echo Something went wrong. Read the message above and open this file again.
  pause
)
