#!/usr/bin/env bash
# S15.13: prototipo de Flatpak de VOZ (usa el CPython y el FFmpeg del runtime).
#
# Uso: packaging/flatpak/build.sh [wheel]
#   wheel            wheel a empaquetar (por defecto se construye uno desde HEAD)
# Variables:
#   VOZ_EXTRAS       extras a incluir, p. ej. "asr-local" (por defecto ninguno)
#   VOZ_WORK         directorio de trabajo (por defecto un mktemp; nunca el repo)
#   VOZ_OUT          directorio del .flatpak resultante (por defecto $VOZ_WORK/out)
# Instala la app SOLO en la instalacion de usuario (--user) para poder probarla:
#   flatpak run dev.voz.Voz --no-browser   |   packaging/common/smoke.sh flatpak run dev.voz.Voz
#   flatpak uninstall --user -y dev.voz.Voz     (para retirarla)
# Necesita: flatpak, org.flatpak.Builder y org.freedesktop.Sdk//25.08 (--user), y red.
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
  mkdir -p "$work/src"
  git -C "$root" archive HEAD | tar -x -C "$work/src"
  (cd "$work/src" && SOURCE_DATE_EPOCH="$(git -C "$root" log -1 --format=%ct)" \
    uv build --wheel --out-dir "$work/dist" >/dev/null)
  wheel="$(ls "$work"/dist/*.whl)"
fi

stage="$work/stage"
[[ ! -e "$stage" ]] || { echo "$stage ya existe; usa un VOZ_WORK nuevo" >&2; exit 1; }
mkdir -p "$stage"
cp "$wheel" "$stage/"
cp "$here/common/voz.svg" "$here/flatpak/dev.voz.Voz.metainfo.xml" "$stage/"
sed 's/^Icon=voz$/Icon=dev.voz.Voz/' "$here/common/voz.desktop" >"$stage/dev.voz.Voz.desktop"
spec=""
[[ -n "$extras" ]] && spec="[$extras]"
sed "s/EXTRAS_SPEC/$spec/" "$here/flatpak/dev.voz.Voz.yml" >"$work/dev.voz.Voz.yml"

t0=$SECONDS
cd "$work"
flatpak run --user org.flatpak.Builder --user --force-clean --install \
  --disable-rofiles-fuse --repo="$work/repo" --state-dir="$work/state" \
  build dev.voz.Voz.yml >"$work/flatpak-builder.log" 2>&1 ||
  { tail -40 "$work/flatpak-builder.log" >&2; exit 1; }
echo "flatpak-builder en $((SECONDS - t0)) s"

name="VOZ-$(basename "$wheel" | cut -d- -f2)${extras:+-$extras}-x86_64.flatpak"
flatpak build-bundle "$work/repo" "$out/$name" dev.voz.Voz >/dev/null
ls -l "$out/$name"
