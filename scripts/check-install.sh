#!/usr/bin/env bash
# S15.03/S15.05: install the wheel with `uv tool install` into temporary tool/XDG
# dirs and run it from a cwd outside the checkout: `voz --help`, `voz doctor --json`,
# then `voz --no-browser --port <free>` must serve `/` and `/api/health` (200) and
# stop cleanly on SIGINT.
#
# Usage: scripts/check-install.sh [wheel]   (default: build one from the checkout)
# Needs network (or a warm uv cache) to resolve runtime dependencies from PyPI.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
server_pid=""
cleanup() {
  [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null || true
  rm -rf "$work"
}
trap cleanup EXIT

wheel="${1:-}"
if [[ -z "$wheel" ]]; then
  (cd "$root" && uv build --wheel --out-dir "$work/dist" >/dev/null)
  wheel="$(ls "$work"/dist/*.whl)"
fi
wheel="$(realpath "$wheel")" # the script changes directory below

mkdir -p "$work"/{tool,bin,config,data,cache,state,cwd}
export UV_TOOL_DIR="$work/tool" UV_TOOL_BIN_DIR="$work/bin"
export XDG_CONFIG_HOME="$work/config" XDG_DATA_HOME="$work/data"
export XDG_CACHE_HOME="$work/cache" XDG_STATE_HOME="$work/state"
cd "$work/cwd"

uv tool install --python 3.12 "$wheel" >/dev/null 2>&1
voz="$work/bin/voz"

"$voz" --help >/dev/null
echo "ok  voz --help"
# doctor exits non-zero when a check fails (e.g. no FFmpeg); only the JSON matters here.
report="$("$voz" doctor --json || true)"
python3 -c 'import json,sys; assert "checks" in json.loads(sys.argv[1])' "$report"
echo "ok  voz doctor --json"

port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
"$voz" --no-browser --port "$port" >"$work/server.log" 2>&1 &
server_pid=$!

fetch() { # <path> -> prints HTTP status
  python3 - "http://127.0.0.1:$port$1" <<'PY'
import sys, urllib.request
try:
    print(urllib.request.urlopen(sys.argv[1], timeout=2).status)
except OSError:
    print(0)
PY
}

for _ in $(seq 1 100); do
  [[ "$(fetch /api/health)" == 200 ]] && break
  kill -0 "$server_pid" 2>/dev/null || { cat "$work/server.log" >&2; exit 1; }
  sleep 0.2
done
[[ "$(fetch /api/health)" == 200 ]] || { echo "/api/health not 200" >&2; cat "$work/server.log" >&2; exit 1; }
[[ "$(fetch /)" == 200 ]] || { echo "/ not 200" >&2; cat "$work/server.log" >&2; exit 1; }
python3 - "http://127.0.0.1:$port/" <<'PY'
import sys, urllib.request
body = urllib.request.urlopen(sys.argv[1], timeout=2).read().decode().lower()
assert "<html" in body and "/assets/" in body, "GET / did not serve the bundled UI"
PY
echo "ok  GET / and GET /api/health -> 200 on 127.0.0.1:$port"

kill -INT "$server_pid"
for _ in $(seq 1 50); do
  kill -0 "$server_pid" 2>/dev/null || break
  sleep 0.2
done
if kill -0 "$server_pid" 2>/dev/null; then
  echo "server did not stop on SIGINT" >&2
  exit 1
fi
wait "$server_pid" && rc=0 || rc=$?
server_pid=""
[[ "$rc" -eq 0 ]] || { echo "server exit code $rc" >&2; cat "$work/server.log" >&2; exit 1; }
echo "ok  clean shutdown (exit 0)"
echo "OK: installed tool works outside the checkout"
