#!/bin/sh
# V. Double-click to open the app (Linux: start-v-linux.sh, which runs this one).
# Python is not required: uv installs itself and fetches Python and the rest.
# FFmpeg is not required either: V downloads a checked copy the first time.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:$PATH"

# Wait for Enter only when a person is looking at a terminal; CI and redirected
# runs (stdin is not a terminal) end at once with the error code.
fail() {
  printf '\n%s\n' "$1"
  if [ -t 0 ]; then
    printf 'Press Enter to close.\n'
    read -r _
  fi
  exit 1
}

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv, this only happens the first time..."
  # The pipeline status is sh's, which succeeds on an empty script when both
  # downloads fail, so check for uv afterwards instead of trusting it.
  { curl -LsSf https://astral.sh/uv/install.sh || wget -qO- https://astral.sh/uv/install.sh; } |
    UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR="$HOME/.local/bin" sh
  command -v uv >/dev/null 2>&1 ||
    fail "Could not install uv. Check your internet connection (curl or wget is needed) and open this file again."
fi

echo "Opening V. The first run downloads what it needs and takes a few minutes."
echo "To close V, close this window or press Ctrl+C."
# `voz` (not `v`): it exists in every environment, including an old .venv that
# predates the `v` entry point; both start the same app. uv run syncs first.
uv run --extra asr-local --extra diarization voz "$@" ||
  fail "Something went wrong. The first run needs an internet connection. Read the message above and open this file again."
