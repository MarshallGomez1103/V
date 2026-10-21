@echo off
rem V. Double-click to open the app.
rem Python is not required: uv installs itself and fetches Python and the rest.
rem FFmpeg is not required either: V downloads a checked copy the first time.
rem On an error the window waits for a key; set VOZ_NO_PAUSE=1 to skip that (CI).
cd /d "%~dp0"
if errorlevel 1 goto fail
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
rem No parenthesised blocks below: a folder name with ")" would break them.
where uv >nul 2>nul && goto run
echo Installing uv, this only happens the first time...
set "UV_NO_MODIFY_PATH=1"
set "UV_INSTALL_DIR=%USERPROFILE%\.local\bin"
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
where uv >nul 2>nul && goto run
echo.
echo Could not install uv. Check your internet connection and open this file again.
goto fail

:run
echo Opening V. The first run downloads what it needs and takes a few minutes.
echo To close V, close this window or press Ctrl+C.
rem "voz" (not "v"): it exists in every environment, including an old .venv that
rem predates the "v" entry point; both start the same app. uv run syncs first.
uv run --extra asr-local --extra diarization voz %*
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo Something went wrong. The first run needs an internet connection.
echo Read the message above and open this file again.
if not defined VOZ_NO_PAUSE pause
exit /b 1
