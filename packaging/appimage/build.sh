#!/usr/bin/env bash
# V AppImage prototype (standalone CPython + wheel + dependencies).
#
# Uso: packaging/appimage/build.sh [wheel]
#   wheel            wheel a empaquetar (por defecto se construye uno desde HEAD)
# Variables:
#   VOZ_EXTRAS       extras a incluir, p. ej. "asr-local" (por defecto ninguno)
#   VOZ_FFMPEG_DIR   directorio con binarios ffmpeg/ffprobe ESTÁTICOS a copiar en
#                    usr/bin (por defecto no se incluye: se usa el FFmpeg del host)
#   VOZ_WORK         directorio de trabajo (por defecto un mktemp; nunca el repo)
#   VOZ_OUT          directorio de salida del .AppImage (por defecto $VOZ_WORK/out)
#   APPIMAGETOOL     ruta a appimagetool (por defecto se descarga a $VOZ_WORK)
# Necesita red para: CPython standalone (uv), dependencias de PyPI y appimagetool.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
here="$root/packaging"
work="${VOZ_WORK:-$(mktemp -d)}"
out="${VOZ_OUT:-$work/out}"
extras="${VOZ_EXTRAS:-}"
mkdir -p "$work" "$out"
echo "trabajo: $work"

wheel="${1:-}"
if [[ -z "$wheel" ]]; then
  # Snapshot de HEAD: los cambios sin commit de otros no afectan al prototipo.
  mkdir -p "$work/src"
  git -C "$root" archive HEAD | tar -x -C "$work/src"
  (cd "$work/src" && SOURCE_DATE_EPOCH="$(git -C "$root" log -1 --format=%ct)" \
    uv build --wheel --out-dir "$work/dist" >/dev/null)
  wheel="$(ls "$work"/dist/*.whl)"
fi
wheel="$(realpath "$wheel")"
spec="$wheel"
[[ -n "$extras" ]] && spec="voz-transcriber[$extras] @ file://$wheel"

appdir="$work/V.AppDir"
[[ ! -e "$appdir" ]] || { echo "$appdir ya existe; usa un VOZ_WORK nuevo" >&2; exit 1; }
mkdir -p "$appdir/usr/lib/voz" "$appdir/usr/bin"

t0=$SECONDS
uv python install 3.12 --install-dir "$work/python-store" >/dev/null 2>&1
py_src="$(ls -d "$work"/python-store/cpython-3.12*-linux-x86_64-gnu | head -1)"
mkdir -p "$appdir/usr/python"
# Sin pruebas de CPython, IDLE ni Tk (no se usan); sin EXTERNALLY-MANAGED.
tar -C "$py_src" --exclude=./lib/python3.12/test --exclude=./lib/python3.12/idlelib \
  --exclude=./lib/python3.12/tkinter --exclude=./lib/python3.12/turtledemo \
  --exclude=EXTERNALLY-MANAGED -cf - . | tar -C "$appdir/usr/python" -xf -

uv pip install --python "$appdir/usr/python/bin/python3" --target "$appdir/usr/lib/voz" \
  --compile-bytecode "$spec" >/dev/null 2>&1
echo "deps+python instalados en $((SECONDS - t0)) s"

if [[ -n "${VOZ_FFMPEG_DIR:-}" ]]; then
  cp "$VOZ_FFMPEG_DIR"/ffmpeg "$VOZ_FFMPEG_DIR"/ffprobe "$appdir/usr/bin/"
fi

install -m755 "$here/appimage/AppRun" "$appdir/AppRun"
install -m644 "$here/common/v.desktop" "$appdir/v.desktop"
install -m644 "$here/common/v.svg" "$appdir/v.svg"
ln -sf v.svg "$appdir/.DirIcon"

tool="${APPIMAGETOOL:-}"
if [[ -z "$tool" ]]; then
  tool="$work/appimagetool"
  [[ -x "$tool" ]] || {
    curl -fsSL -o "$tool" \
      https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$tool"
  }
fi

name="V-$(python3 -c 'import re,sys; print(re.search(r"-(\d[^-]*)-", sys.argv[1].rsplit("/",1)[1]).group(1))' "$wheel")${extras:+-$extras}-x86_64.AppImage"
t1=$SECONDS
ARCH=x86_64 "$tool" --appimage-extract-and-run "$appdir" "$out/$name" >"$work/appimagetool.log" 2>&1 ||
  { cat "$work/appimagetool.log" >&2; exit 1; }
echo "appimagetool en $((SECONDS - t1)) s; total $((SECONDS - t0)) s"
ls -l "$out/$name"
