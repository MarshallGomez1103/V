#!/usr/bin/env bash
# S16.02: capturas PNG reales de la app corriendo en esta maquina (docs/demo.md).
#
# Aisla todo en un directorio temporal: XDG_* propios (nunca toca ~/.local/share/voz,
# ~/.config/voz ni ~/.local/state/voz), arranca `voz` en un puerto libre, genera un
# audio de demo con espeak-ng (dos voces), importa por la API el modelo turbo ya
# instalado en el cache de Buzz (hardlink, solo lectura; no descarga nada) y maneja
# la UI con Chrome (flatpak, headless) por CDP (scripts/capture-screenshots.mjs).
# Sin modelo local disponible, capturas solo las pantallas que no lo necesitan.
#
# Uso: scripts/capture-screenshots.sh [directorio-de-salida]
# Requiere: uv, node >= 22, ffmpeg, espeak-ng, flatpak com.google.Chrome.
# Variables: VOZ_CMD (por defecto `uv run --no-sync voz`), CAPTURE_MODEL (por
# defecto `turbo`), CHROME_CMD (por defecto `flatpak run com.google.Chrome`).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$(realpath -m "${1:-$root/docs/assets/screenshots}")"
model="${CAPTURE_MODEL:-turbo}"
voz_cmd="${VOZ_CMD:-uv run --no-sync voz}"
chrome_cmd="${CHROME_CMD:-flatpak run com.google.Chrome}"

for tool in uv node ffmpeg espeak-ng; do
  command -v "$tool" >/dev/null || { echo "falta $tool" >&2; exit 1; }
done
[[ -x "$root/.bootstrap/bin/uv" ]] && export PATH="$root/.bootstrap/bin:$PATH"

# El temporal vive bajo $HOME (mismo sistema de archivos que el cache de Buzz: el
# modelo se enlaza con hardlink, sin copiar GB). El perfil de Chrome va bajo
# ~/Downloads porque el sandbox flatpak solo puede escribir ahi.
work="$(mktemp -d "$HOME/.cache/voz-capture.XXXXXX")"
profile="$(mktemp -d "$HOME/Downloads/voz-capture-chrome.XXXXXX")"
server_pid=""
cleanup() {
  [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null || true
  [[ -n "$server_pid" ]] && wait "$server_pid" 2>/dev/null || true
  # solo borramos lo que creamos nosotros, con prefijo y padre comprobados
  [[ "$work" == "$HOME"/.cache/voz-capture.* ]] && rm -rf -- "$work"
  [[ "$profile" == "$HOME"/Downloads/voz-capture-chrome.* ]] && rm -rf -- "$profile"
  return 0
}
trap cleanup EXIT INT TERM

mkdir -p "$work"/{config,data,cache,state} "$out"
# uv tambien respeta XDG_*: apuntamos su cache/CPython a los reales para no repetir descargas
export UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/.cache/uv}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$HOME/.local/share/uv/python}"
export XDG_CONFIG_HOME="$work/config" XDG_DATA_HOME="$work/data"
export XDG_CACHE_HOME="$work/cache" XDG_STATE_HOME="$work/state"

# --- audio de demo: dos voces alternando, con pausas ---
(
  cd "$work"
  espeak-ng -v es+f3 -s 150 -w a1.wav "Buenos días. Hoy vamos a repasar la entrega del proyecto de ingeniería."
  espeak-ng -v es+m3 -s 150 -w b1.wav "Perfecto. Primero revisamos el presupuesto y después fijamos la fecha de la reunión."
  espeak-ng -v es+f3 -s 150 -w a2.wav "De acuerdo. Yo preparo el informe y tú confirmas el calendario."
  ffmpeg -v error -f lavfi -i anullsrc=r=22050:cl=mono -t 0.7 pausa.wav
  printf "file '%s'\n" a1.wav pausa.wav b1.wav pausa.wav a2.wav >lista.txt
  ffmpeg -v error -y -f concat -safe 0 -i lista.txt -ar 22050 -ac 1 reunion-demo.wav
)

# --- servidor en un puerto libre ---
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
base="http://127.0.0.1:$port"
# shellcheck disable=SC2086
(cd "$root" && exec $voz_cmd --no-browser --port "$port") >"$work/server.log" 2>&1 &
server_pid=$!

api() { # <metodo> <ruta> [json] -> imprime el cuerpo; falla si HTTP >= 400
  curl -fsS -X "$1" -H 'Content-Type: application/json' ${3:+-d "$3"} "$base$2"
}
for _ in $(seq 1 150); do
  curl -fsS "$base/api/health" >/dev/null 2>&1 && break
  kill -0 "$server_pid" 2>/dev/null || { cat "$work/server.log" >&2; exit 1; }
  sleep 0.2
done
curl -fsS "$base/api/health" >/dev/null || { cat "$work/server.log" >&2; exit 1; }
echo "ok  servidor en $base (XDG temporal)"

# --- modelo local: importar desde el cache de Buzz (solo lectura, sin descargas) ---
have_model=0
if api GET /api/models | python3 -c '
import json, sys
key = "faster-whisper:" + sys.argv[1]
m = {x["key"]: x for x in json.load(sys.stdin)["models"]}
sys.exit(0 if key in m and m[key]["external"] and m[key]["runtime_available"] else 1)' "$model"; then
  task="$(api POST "/api/models/faster-whisper:$model/install" \
    '{"method":"import","origin":"buzz","confirm":true}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
  for _ in $(seq 1 600); do
    state="$(api GET "/api/model-tasks/$task" | python3 -c 'import json,sys; print(json.load(sys.stdin)["state"])')"
    [[ "$state" == completed || "$state" == failed || "$state" == cancelled ]] && break
    sleep 0.5
  done
  [[ "$state" == completed ]] && have_model=1
  echo "ok  importacion del modelo $model desde Buzz: $state"
else
  echo "aviso: no hay copia de $model en el cache de Buzz (o falta el extra asr-local): solo capturas sin transcripcion" >&2
fi

# --- capturas ---
CAPTURE_URL="$base" CAPTURE_AUDIO="$work/reunion-demo.wav" CAPTURE_OUT="$out" \
CAPTURE_PROFILE="$profile" CAPTURE_MODEL="$model" CAPTURE_HAVE_MODEL="$have_model" \
CHROME_CMD="$chrome_cmd" node "$root/scripts/capture-screenshots.mjs"

echo "OK: capturas en $out"
