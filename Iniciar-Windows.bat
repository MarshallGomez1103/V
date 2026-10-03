@echo off
rem VOZ. Doble clic para abrir la aplicacion.
rem No hace falta tener Python: uv se instala solo y baja Python y lo demas.
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo Instalando uv, solo pasa la primera vez...
  set UV_NO_MODIFY_PATH=1
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
)
echo Abriendo VOZ. La primera vez descarga lo necesario y tarda unos minutos.
echo Para cerrar VOZ, cierra esta ventana o pulsa Ctrl+C.
uv run --extra asr-local --extra diarization voz %*
if errorlevel 1 (
  echo.
  echo Algo fallo. Lee el mensaje de arriba y vuelve a abrir este archivo.
  pause
)
