#!/bin/sh
# DEPRECATED: use start-v-linux.sh. This wrapper stays for one release.
exec sh "$(dirname "$0")/start-v-linux.sh" "$@"
