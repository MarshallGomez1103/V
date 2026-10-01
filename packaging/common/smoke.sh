#!/usr/bin/env bash
# Prueba de humo de un empaquetado: arranca el comando dado con XDG temporales y
# mide el tiempo hasta que /api/health responde 200 (la UI en / también).
# Uso: packaging/common/smoke.sh <comando...>   p. ej. ./VOZ-0.1.0-x86_64.AppImage
# El comando recibe `--no-browser --port <libre>` al final.
# Flatpak: packaging/common/smoke.sh flatpak run dev.voz.Voz (usa su propio XDG en ~/.var/app).
set -euo pipefail

work="$(mktemp -d)"
pid=""
cleanup() {
  [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  rm -rf "$work"
}
trap cleanup EXIT
mkdir -p "$work"/{config,data,cache,state,cwd}
# Flatpak fija su propio XDG y localiza la app via XDG_DATA_HOME: no se reasigna.
if [[ "$1" != flatpak ]]; then
  export XDG_CONFIG_HOME="$work/config" XDG_DATA_HOME="$work/data"
  export XDG_CACHE_HOME="$work/cache" XDG_STATE_HOME="$work/state"
fi
cd "$work/cwd"

port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
start=$(date +%s.%N)
"$@" --no-browser --port "$port" >"$work/server.log" 2>&1 &
pid=$!

status() { # <ruta> -> estado HTTP o 0
  python3 - "http://127.0.0.1:$port$1" <<'PY'
import sys, urllib.request
try:
    print(urllib.request.urlopen(sys.argv[1], timeout=2).status)
except OSError:
    print(0)
PY
}

for _ in $(seq 1 300); do
  [[ "$(status /api/health)" == 200 ]] && break
  kill -0 "$pid" 2>/dev/null || { cat "$work/server.log" >&2; exit 1; }
  sleep 0.1
done
[[ "$(status /api/health)" == 200 ]] || { echo "/api/health no respondió 200" >&2; cat "$work/server.log" >&2; exit 1; }
end=$(date +%s.%N)
[[ "$(status /)" == 200 ]] || { echo "/ no respondió 200" >&2; exit 1; }
printf 'ok  /api/health 200 en %.2f s (puerto %s)\n' "$(echo "$end - $start" | bc -l)" "$port"
kill -INT "$pid"
wait "$pid" && echo "ok  parada limpia (exit 0)" || echo "parada con exit $?"
pid=""
