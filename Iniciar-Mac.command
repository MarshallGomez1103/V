#!/bin/sh
# VOZ. Doble clic para abrir la aplicación (Linux: Iniciar-Linux.sh).
# No hace falta tener Python: uv se instala solo y baja Python y lo demás.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:$PATH"

falla() {
  printf '\n%s\nPulsa Enter para cerrar.\n' "$1"
  read -r _
  exit 1
}

if ! command -v uv >/dev/null 2>&1; then
  echo "Instalando uv, solo pasa la primera vez..."
  { curl -LsSf https://astral.sh/uv/install.sh || wget -qO- https://astral.sh/uv/install.sh; } |
    UV_NO_MODIFY_PATH=1 sh ||
    falla "No se pudo instalar uv. Comprueba la conexión a internet y vuelve a abrir este archivo."
fi

echo "Abriendo VOZ. La primera vez descarga lo necesario y tarda unos minutos."
echo "Para cerrar VOZ, cierra esta ventana o pulsa Ctrl+C."
uv run --extra asr-local --extra diarization voz "$@" ||
  falla "Algo falló. Lee el mensaje de arriba y vuelve a abrir este archivo."
