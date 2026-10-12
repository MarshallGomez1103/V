#!/bin/sh
# DEPRECATED: use Start-V-macOS.command. This wrapper stays for one release.
exec sh "$(dirname "$0")/Start-V-macOS.command" "$@"
