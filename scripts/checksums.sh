#!/usr/bin/env bash
# S15.07: write dist/SHA256SUMS for every artifact in the directory and verify it.
# Usage: scripts/checksums.sh [dist-dir]   (default: dist)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dir="${1:-$root/dist}"
[[ -d "$dir" ]] || { echo "no such directory: $dir" >&2; exit 1; }

cd "$dir"
files=()
while IFS= read -r -d '' file; do
  files+=("${file#./}")
done < <(find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z)
[[ "${#files[@]}" -gt 0 ]] || { echo "no artifacts in $dir" >&2; exit 1; }

sha256sum -- "${files[@]}" > SHA256SUMS
sha256sum --check --quiet SHA256SUMS
cat SHA256SUMS
