#!/bin/sh
# V. Linux launcher: same startup as macOS (Start-V-macOS.command).
exec sh "$(dirname "$0")/Start-V-macOS.command" "$@"
