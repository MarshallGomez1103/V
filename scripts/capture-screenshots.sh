#!/usr/bin/env bash
# V10-06S: capturas PNG reales de V corriendo en esta maquina, en ingles (docs/demo.md).
#
# Aisla todo en un directorio temporal: XDG_* propios (nunca toca ~/.local/share/voz,
# ~/.config/voz ni ~/.local/state/voz), arranca `voz` en un puerto libre (nunca 8765),
# genera audios de demo en ingles con Kokoro (sherpa-onnx del entorno, voces
# sinteticas, textos inventados), importa por la API el modelo faster-whisper ya
# presente en el cache de Hugging Face/Buzz (hardlink, solo lectura; no descarga nada),
# copia los modelos de hablantes, importa la carpeta de Kokoro como modelo propio y
# maneja la UI con Chrome (flatpak, headless) por CDP (scripts/capture-screenshots.mjs).
#
# Uso: scripts/capture-screenshots.sh [directorio-de-salida]
# Requiere: uv, node >= 22, ffmpeg, curl, flatpak com.google.Chrome y dos carpetas:
#   CAPTURE_KOKORO_DIR       kokoro-int8-multi-lang-v1_0 ya extraido (se lee, no se toca)
#   CAPTURE_DIARIZATION_DIR  carpeta con pyannote-segmentation-3-0.onnx y
#                            wespeaker_en_voxceleb_resnet34_LM.onnx (se COPIA al temporal)
# Variables opcionales: VOZ_CMD (por defecto `uv run --no-sync voz`), CAPTURE_MODEL
# (por defecto `base`), BUZZ_MODEL_ROOT (por defecto ~/.cache/huggingface/hub),
# CAPTURE_HF_LINK (enlace para «Check link»; solo metadatos, nunca se instala) y
# CHROME_CMD (por defecto `flatpak run com.google.Chrome`).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$(realpath -m "${1:-$root/docs/assets/screenshots}")"
model="${CAPTURE_MODEL:-base}"
voz_cmd="${VOZ_CMD:-uv run --no-sync voz}"
chrome_cmd="${CHROME_CMD:-flatpak run com.google.Chrome}"
kokoro="${CAPTURE_KOKORO_DIR:-}"
diar="${CAPTURE_DIARIZATION_DIR:-}"

for tool in uv node ffmpeg curl; do
  command -v "$tool" >/dev/null || { echo "falta $tool" >&2; exit 1; }
done
[[ -x "$root/.bootstrap/bin/uv" ]] && export PATH="$root/.bootstrap/bin:$PATH"
[[ -f "$kokoro/model.int8.onnx" && -f "$kokoro/voices.bin" ]] || {
  echo "CAPTURE_KOKORO_DIR debe apuntar a kokoro-int8-multi-lang-v1_0 extraido" >&2; exit 1; }
[[ -f "$diar/pyannote-segmentation-3-0.onnx" && -f "$diar/wespeaker_en_voxceleb_resnet34_LM.onnx" ]] || {
  echo "CAPTURE_DIARIZATION_DIR debe tener los dos .onnx de hablantes" >&2; exit 1; }

# El temporal vive bajo $HOME (mismo sistema de archivos que el cache de modelos: el
# modelo se enlaza con hardlink, sin copiar). El perfil de Chrome va bajo ~/Downloads
# porque el sandbox flatpak solo puede escribir ahi.
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

mkdir -p "$work"/{home,config,data,cache,state,audio} "$out"
# uv tambien respeta XDG_*: apuntamos su cache/CPython a los reales para no repetir descargas
export UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/.cache/uv}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$HOME/.local/share/uv/python}"
export BUZZ_MODEL_ROOT="${BUZZ_MODEL_ROOT:-$HOME/.cache/huggingface/hub}"
export XDG_CONFIG_HOME="$work/config" XDG_DATA_HOME="$work/data"
export XDG_CACHE_HOME="$work/cache" XDG_STATE_HOME="$work/state"

# --- hablantes: copia de los dos .onnx + el manifiesto que escribiria la instalacion ---
diar_dir="$work/data/voz/models/diarization"
mkdir -p "$diar_dir"
cp -- "$diar/pyannote-segmentation-3-0.onnx" "$diar/wespeaker_en_voxceleb_resnet34_LM.onnx" "$diar_dir/"
chmod u+w "$diar_dir"/*.onnx
(cd "$root" && uv run --no-sync python -I - "$diar_dir") <<'PY'
import json, sys
from datetime import UTC, datetime
from pathlib import Path
from voz.infrastructure.diarization import models as m

folder = Path(sys.argv[1])
manifest = {
    "sources": {a.name: a.sha256 for a in (m.SEGMENTATION_ARCHIVE, m.EMBEDDING_MODEL)},
    "files": {n: (folder / n).stat().st_size for n in (m.SEGMENTATION_FILE, m.EMBEDDING_FILE)},
    "installed_at": datetime.now(UTC).isoformat(),
}
(folder / ".voz-diarization.json").write_text(json.dumps(manifest, indent=2))
PY

# --- audios de demo: Kokoro en CPU, voces sinteticas, textos inventados ---
# Cada linea: voz|texto|clip. Los clips se unen con pausas en un .wav por proyecto.
(cd "$root" && uv run --no-sync python -I - "$kokoro" "$work/audio") <<'PY'
import sys, wave
from pathlib import Path

import numpy
import sherpa_onnx
from voz.infrastructure.tts import families

LINES = """\
af_heart|Good morning, everyone. Today we need to plan the launch of the open source audio library.|ps1
am_michael|Sounds good. I finished the documentation draft yesterday, and the examples are ready for review.|ps2
af_heart|Great. Let's freeze the features on Friday and publish the first release next Tuesday.|ps3
am_michael|Agreed. I will write the release notes and check the test results before then.|ps4
af_sarah|In today's lecture we look at how sound travels. A sound wave is a pattern of pressure changes moving through the air.|ln1
am_adam|Welcome back to the show. This week we are talking about small vegetable gardens.|pi1
af_bella|Thanks for having me. Let's start with tomatoes, because they are easier than people think.|pi2"""

source, out = Path(sys.argv[1]), Path(sys.argv[2])
files = families.discover_files("kokoro", source)
names = families.speaker_names(families.read_onnx_metadata(files["model"]))
engines = {}
for line in LINES.splitlines():
    voice, text, clip = line.split("|")
    lang = families.kokoro_lang(voice)
    if lang not in engines:
        spec = families.model_config("kokoro", files, lang=lang)
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                **{spec.field: getattr(sherpa_onnx, spec.config_class)(**spec.kwargs)},
                num_threads=4,
                provider="cpu",
            )
        )
        engines[lang] = sherpa_onnx.OfflineTts(config)
    audio = engines[lang].generate(text, sid=names.index(voice), speed=1.0)
    pcm = (numpy.clip(numpy.asarray(audio.samples), -1, 1) * 32767).astype("<i2")
    with wave.open(str(out / (clip + ".wav")), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(audio.sample_rate)
        output.writeframes(pcm.tobytes())
PY
(
  cd "$work/audio"
  ffmpeg -v error -f lavfi -i anullsrc=r=24000:cl=mono -t 0.6 pause.wav
  join() { # <salida> <clips...>
    local target="$1"; shift
    printf "file '%s.wav'\nfile 'pause.wav'\n" "$@" | head -n -1 >"$target.txt"
    ffmpeg -v error -y -f concat -safe 0 -i "$target.txt" -ar 24000 -ac 1 "$target.wav"
  }
  join product-sync ps1 ps2 ps3 ps4
  join lecture-notes ln1
  join podcast-intro pi1 pi2
)
echo "ok  audios de demo: $(cd "$work/audio" && ls product-sync.wav lecture-notes.wav podcast-intro.wav | tr '\n' ' ')"

# --- servidor en un puerto libre ---
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
[[ "$port" != 8765 ]] || { echo "puerto 8765 reservado; repite" >&2; exit 1; }
base="http://127.0.0.1:$port"
# HOME temporal solo para el servidor: asi no ve copias de modelos del HOME real (p. ej.
# el cache flatpak de Buzz); uv y BUZZ_MODEL_ROOT ya apuntan explicitamente a lo real.
# shellcheck disable=SC2086
(cd "$root" && HOME="$work/home" exec $voz_cmd --no-browser --port "$port") >"$work/server.log" 2>&1 &
server_pid=$!

api() { # <metodo> <ruta> [json] -> imprime el cuerpo; falla si HTTP >= 400
  curl -fsS -X "$1" -H 'Content-Type: application/json' ${3:+-d "$3"} "$base$2"
}
json() { python3 -c "import json, sys; print(json.load(sys.stdin)$1)"; }
wait_task() { # <id> -> imprime el estado final
  local state=""
  for _ in $(seq 1 600); do
    state="$(api GET "/api/model-tasks/$1" | json '["state"]')"
    [[ "$state" == completed || "$state" == failed || "$state" == cancelled ]] && break
    sleep 0.5
  done
  echo "$state"
}
for _ in $(seq 1 150); do
  curl -fsS "$base/api/health" >/dev/null 2>&1 && break
  kill -0 "$server_pid" 2>/dev/null || { cat "$work/server.log" >&2; exit 1; }
  sleep 0.2
done
curl -fsS "$base/api/health" >/dev/null || { cat "$work/server.log" >&2; exit 1; }
echo "ok  servidor en $base (XDG temporal)"

# --- transcripcion: importar desde el cache local (solo lectura, sin descargas) ---
task="$(api POST "/api/models/faster-whisper:$model/install" \
  '{"method":"import","origin":"buzz","confirm":true}' | json '["id"]')"
state="$(wait_task "$task")"
echo "ok  importacion de faster-whisper $model desde el cache local: $state"
[[ "$state" == completed ]] || exit 1

# --- sintesis: la carpeta de Kokoro como modelo propio (se copia; el original no cambia) ---
preview="$(api POST /api/models/custom/preview "$(python3 -c 'import json, sys; print(json.dumps({
  "source_type": "folder", "source": sys.argv[1], "engine": "sherpa-onnx-tts", "family": "kokoro",
  "display_name": "Kokoro multilingual v1.0", "license": "Apache-2.0"}))' "$kokoro")" | json '["id"]')"
task="$(api POST /api/models/custom/install "{\"preview_id\":\"$preview\",\"confirm\":true}" | json '["id"]')"
state="$(wait_task "$task")"
echo "ok  importacion de Kokoro (carpeta local): $state"
[[ "$state" == completed ]] || exit 1

# --- capturas ---
CAPTURE_URL="$base" CAPTURE_AUDIO_DIR="$work/audio" CAPTURE_OUT="$out" \
CAPTURE_PROFILE="$profile" CAPTURE_MODEL="$model" CHROME_CMD="$chrome_cmd" \
CAPTURE_HF_LINK="${CAPTURE_HF_LINK:-https://huggingface.co/Systran/faster-whisper-base}" \
node "$root/scripts/capture-screenshots.mjs"

# «Check link» solo lee metadatos: aqui solo deben estar los modelos importados arriba.
echo "modelos en el temporal: $(api GET /api/models | python3 -c '
import json, sys
print(", ".join(m["key"] for m in json.load(sys.stdin)["models"] if m["installed"]))')"
echo "OK: capturas en $out"
