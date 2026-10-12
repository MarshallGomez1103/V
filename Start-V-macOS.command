#!/bin/sh
# V. Double-click to open the app (Linux: start-v-linux.sh, which runs this one).
# Python is not required: uv installs itself and fetches Python and the rest.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:$PATH"

fail() {
  printf '\n%s\nPress Enter to close.\n' "$1"
  read -r _
  exit 1
}

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv, this only happens the first time..."
  { curl -LsSf https://astral.sh/uv/install.sh || wget -qO- https://astral.sh/uv/install.sh; } |
    UV_NO_MODIFY_PATH=1 sh ||
    fail "Could not install uv. Check your internet connection and open this file again."
fi

echo "Opening V. The first run downloads what it needs and takes a few minutes."
echo "To close V, close this window or press Ctrl+C."
# `voz` (not `v`): it exists in every environment, including an old .venv that
# predates the `v` entry point; both start the same app. uv run syncs first.
uv run --extra asr-local --extra diarization voz "$@" ||
  fail "Something went wrong. Read the message above and open this file again."
