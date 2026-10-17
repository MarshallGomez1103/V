#!/usr/bin/env bash
# Build the experimental V Flatpak using the runtime's CPython and FFmpeg.
#
# Usage: packaging/flatpak/build.sh [wheel]
#   wheel            wheel to package (defaults to a build from HEAD)
# Environment:
#   VOZ_EXTRAS       optional extras, e.g. "asr-local" (defaults to none)
#   VOZ_WORK         work directory (defaults to mktemp; never the checkout)
#   VOZ_OUT          bundle directory (defaults to $VOZ_WORK/out)
# Creates a local bundle without installing the application on the host.
# Requires flatpak, org.flatpak.Builder, org.freedesktop.Sdk//25.08 (--user),
# and network access for build dependencies.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
here="$root/packaging"
work="${VOZ_WORK:-$(mktemp -d)}"
out="${VOZ_OUT:-$work/out}"
extras="${VOZ_EXTRAS:-}"
mkdir -p "$work" "$out"
echo "Work directory: $work"

wheel="${1:-}"
if [[ -z "$wheel" ]]; then
  mkdir -p "$work/src"
  git -C "$root" archive HEAD | tar -x -C "$work/src"
  (cd "$work/src" && SOURCE_DATE_EPOCH="$(git -C "$root" log -1 --format=%ct)" \
    uv build --wheel --out-dir "$work/dist" >/dev/null)
  wheel="$(ls "$work"/dist/*.whl)"
fi

stage="$work/stage"
[[ ! -e "$stage" ]] || { echo "Stage already exists; use a fresh VOZ_WORK" >&2; exit 1; }
mkdir -p "$stage"
cp "$wheel" "$stage/"
cp "$here/common/v.svg" "$stage/io.github.marshallgomez1103.v.svg"
cp "$here/flatpak/io.github.marshallgomez1103.v.metainfo.xml" "$stage/"
sed 's/^Icon=v$/Icon=io.github.marshallgomez1103.v/' "$here/common/v.desktop" >"$stage/io.github.marshallgomez1103.v.desktop"
spec=""
[[ -n "$extras" ]] && spec="[$extras]"
sed "s/EXTRAS_SPEC/$spec/" "$here/flatpak/io.github.marshallgomez1103.v.yml" >"$work/io.github.marshallgomez1103.v.yml"

t0=$SECONDS
cd "$work"
flatpak run --user org.flatpak.Builder --user --force-clean \
  --disable-rofiles-fuse --repo="$work/repo" --state-dir="$work/state" \
  build io.github.marshallgomez1103.v.yml >"$work/flatpak-builder.log" 2>&1 ||
  { tail -40 "$work/flatpak-builder.log" >&2; exit 1; }
echo "flatpak-builder completed in $((SECONDS - t0)) s"

name="V-$(basename "$wheel" | cut -d- -f2)${extras:+-$extras}-x86_64.flatpak"
flatpak build-bundle "$work/repo" "$out/$name" io.github.marshallgomez1103.v >/dev/null
ls -l "$out/$name"
