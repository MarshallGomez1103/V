#!/usr/bin/env bash
# S15.01/S15.02: build wheel + sdist several times and require identical SHA-256.
#
# The working tree is snapshotted once, so edits made while this runs cannot cause
# false negatives. Builds (1) and (2) use one copy; build (3) uses a second copy at
# another path with fresh mtimes and a different umask, proving the artifacts do not
# depend on location or file times. Needs `uv` and either network or a warm uv cache
# (to resolve the hatchling build requirement).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if [[ -z "${SOURCE_DATE_EPOCH:-}" ]]; then
  SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
fi
export SOURCE_DATE_EPOCH

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

tar --exclude=./.venv --exclude=./.git --exclude=./dist --exclude=node_modules \
  --exclude=__pycache__ -cf "$work/snapshot.tar" .
mkdir -p "$work/one" "$work/two/nested"
tar -xf "$work/snapshot.tar" -C "$work/one"
sleep 1 # different mtimes between the two copies
(umask 077 && tar --touch -xf "$work/snapshot.tar" -C "$work/two/nested")

build() { # <name> <project dir>
  (cd "$2" && uv build --out-dir "$work/$1" >"$work/$1.log" 2>&1) ||
    { cat "$work/$1.log" >&2; exit 1; }
}

build a "$work/one"
build b "$work/one"
(umask 077 && build c "$work/two/nested")

status=0
for artifact in "$work"/a/*; do
  name="$(basename "$artifact")"
  sums="$(cd "$work" && sha256sum "a/$name" "b/$name" "c/$name" | cut -d' ' -f1 | sort -u)"
  if [[ "$(wc -l <<<"$sums")" -ne 1 ]]; then
    echo "NOT REPRODUCIBLE: $name" >&2
    (cd "$work" && sha256sum "a/$name" "b/$name" "c/$name") >&2
    status=1
  else
    echo "reproducible  $sums  $name"
  fi
done

if [[ "$status" -eq 0 ]]; then
  echo "OK: SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH, 3 builds, identical artifacts"
fi
exit "$status"
