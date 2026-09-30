#!/usr/bin/env bash
# S16.19: pre-release audit of the working tree AND the whole git history for
# secrets, personal paths, private data and oversized/binary files.
#
# Usage: scripts/audit-secrets.sh [--tree-only] [--max-kib N]
#   --tree-only   skip the history scan (fast; useful as a pre-commit check)
#   --max-kib N   size threshold for "large file" findings (default 1024)
# Env: VOZ_AUDIT_PATH_ALLOW  ERE of personal-path placeholders to ignore
#      (default: /home/(user|runner|example|voz|you)\b).
#
# Needs only bash, git and coreutils. It NEVER prints a matched secret: every
# finding is "<kind> <commit> <path>", so the output is safe to paste into an
# issue. Exit 1 when a HIGH finding exists; REVIEW findings (matches under
# tests/, usually fake fixtures) and INFO lines do not fail the run.
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git checkout" >&2; exit 2; }

history=1
max_kib=1024
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tree-only) history=0 ;;
    --max-kib) max_kib="${2:?--max-kib needs a number}"; shift ;;
    -h | --help) sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

high=0
review=0
note() { printf '%s\n' "$*"; }
finding() { # <HIGH|REVIEW> <text>
  if [[ "$1" == HIGH ]]; then high=$((high + 1)); else review=$((review + 1)); fi
  printf '  [%s] %s\n' "$1" "$2"
}
classify() { # path -> HIGH (shipped code/docs) or REVIEW (tests/fixtures)
  [[ "$1" == tests/* || "$1" == */tests/* || "$1" == *.test.* ]] && echo REVIEW || echo HIGH
}

# name|ERE (POSIX, used by both `git grep -E` and `git log -G`)
secret_patterns=(
  "openai/anthropic-style key|sk-[A-Za-z0-9_-]{20,}"
  "elevenlabs key|sk_[a-f0-9]{40,}"
  "elevenlabs header with value|xi-api-key['\"]?[[:space:]]*[:=][[:space:]]*['\"][A-Za-z0-9]{16,}"
  "huggingface token|hf_[A-Za-z0-9]{30,}"
  "aws access key id|(AKIA|ASIA)[0-9A-Z]{16}"
  "private key block|-----BEGIN [A-Z ]*PRIVATE KEY-----"
  "github token|gh[pousr]_[A-Za-z0-9]{36,}"
  "github fine-grained token|github_pat_[A-Za-z0-9_]{22,}"
  "slack token|xox[baprs]-[A-Za-z0-9-]{10,}"
  "google api key|AIza[0-9A-Za-z_-]{35}"
  "bearer token|Bearer [A-Za-z0-9._~+/-]{24,}"
  "assigned secret literal|(api[_-]?key|secret|token|passw(or)?d)['\"]?[[:space:]]*[:=][[:space:]]*['\"][A-Za-z0-9/+_-]{20,}['\"]"
)
path_re='(/home/[A-Za-z0-9._-]+|/var/home/[A-Za-z0-9._-]+|/Users/[A-Za-z0-9._-]+)'
path_allow="${VOZ_AUDIT_PATH_ALLOW:-/home/(user|runner|example|voz|you)([^A-Za-z0-9._-]|$)}"
media_re='\.(wav|mp3|m4a|mp4|webm|flac|aac|aiff?|ogg|opus|mkv|mov|avi|mpe?g|mpga|gguf|ggml|safetensors|ckpt|onnx|pt|pth|sqlite3?|db|db-wal|db-shm|zip|tar|gz|bz2|xz|7z)$'
secret_files_re='(^|/)(\.env(\..*)?|.*\.env|credentials.*\.json|service-account.*\.json|id_(rsa|ed25519)(\..*)?|.*\.(key|pem|p12|pfx))$'
env_example_re='(^|/)\.env\.example$'

note "== 1. Working tree (tracked + untracked, not ignored) =="
for entry in "${secret_patterns[@]}"; do
  name="${entry%%|*}"; regex="${entry#*|}"
  while IFS= read -r path; do
    [[ -z "$path" || "$path" == scripts/audit-secrets.sh ]] && continue
    finding "$(classify "$path")" "tree: $name in $path"
  done < <(git grep -lIE --untracked -e "$regex" -- . 2>/dev/null || true)
done

while IFS= read -r path; do
  [[ -z "$path" || "$path" == scripts/audit-secrets.sh ]] && continue
  hits="$(git grep -hIoE --untracked -e "$path_re" -- "$path" 2>/dev/null | grep -Ev "$path_allow" | wc -l)"
  [[ "$hits" -gt 0 ]] && finding "$(classify "$path")" "tree: personal path ($hits occurrence(s)) in $path"
done < <(git grep -lIE --untracked -e "$path_re" -- . 2>/dev/null || true)

while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  [[ "$path" =~ $env_example_re ]] && continue
  [[ "$path" =~ $secret_files_re ]] && finding HIGH "tree: secret-looking file is tracked or unignored: $path"
  [[ "$path" =~ $media_re && "$path" != tests/fixtures/* ]] &&
    finding HIGH "tree: media/db/model/archive file outside tests/fixtures: $path"
done < <(git ls-files --cached --others --exclude-standard)

tracked_ai="$(git ls-files --cached -- .ai | wc -l)"
[[ "$tracked_ai" -gt 0 ]] && finding HIGH "tree: .ai/ has $tracked_ai tracked file(s); it must never be versioned"
git check-ignore -q .ai/ || finding HIGH "tree: .ai/ is not ignored by .gitignore"

limit=$((max_kib * 1024))
while read -r _ _ _ size path; do
  [[ "$size" =~ ^[0-9]+$ && "$size" -gt "$limit" ]] && finding REVIEW "tree: large file (${size} bytes) $path"
done < <(git ls-tree -r -l HEAD)

note "== 2. Git history ($(git rev-list --all | wc -l) commits) =="
if [[ "$history" -eq 0 ]]; then
  note "  (skipped: --tree-only)"
else
  ai_commits="$(git log --all --oneline -- .ai | wc -l)"
  [[ "$ai_commits" -gt 0 ]] && finding HIGH "history: .ai/ appears in $ai_commits commit(s)"

  for entry in "${secret_patterns[@]}"; do
    name="${entry%%|*}"; regex="${entry#*|}"
    while read -r tag a b; do
      case "$tag" in
        commit) commit="$a" ;;
        file) [[ "$a" == scripts/audit-secrets.sh ]] || finding "$(classify "$a")" "history: $name in $commit $a" ;;
      esac
    done < <(git log --all -G"$regex" --no-color --format='commit %h' --name-only |
      awk '/^commit /{print; next} NF{print "file " $0}')
  done

  commit=""
  while read -r tag a; do
    case "$tag" in
      commit) commit="$a" ;;
      file)
        [[ "$a" == scripts/audit-secrets.sh ]] && continue
        hits="$(git show "$commit" -- "$a" 2>/dev/null | grep -E '^\+' | grep -Eo "$path_re" | grep -Ev "$path_allow" | wc -l)"
        [[ "$hits" -gt 0 ]] && finding "$(classify "$a")" "history: personal path in $commit $a"
        ;;
    esac
  done < <(git log --all -G"$path_re" --no-color --format='commit %h' --name-only |
    awk '/^commit /{print; next} NF{print "file " $0}')

  commit=""
  while read -r tag a; do
    case "$tag" in
      commit) commit="$a" ;;
      file)
        [[ "$a" =~ $env_example_re ]] && continue
        [[ "$a" =~ $secret_files_re ]] && finding HIGH "history: secret-looking file added in $commit: $a"
        [[ "$a" =~ $media_re && "$a" != tests/fixtures/* ]] &&
          finding HIGH "history: media/db/model/archive file added in $commit: $a"
        ;;
    esac
  done < <(git log --all --diff-filter=A --name-only --format='commit %h' |
    awk '/^commit /{print; next} NF{print "file " $0}')

  while read -r kind _ size rest; do
    [[ "$kind" == blob && "$size" -gt "$limit" ]] && finding REVIEW "history: large blob (${size} bytes) ${rest:-unnamed}"
  done < <(git rev-list --objects --all |
    git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)')

  note "  INFO authors/committers that become public with the history:"
  git log --all --format='%an <%ae>%n%cn <%ce>' | sort | uniq -c | sed 's/^/    /'
fi

note "== 3. Ignored files present on this machine (never shipped; awareness only) =="
while IFS= read -r path; do
  case "$path" in
    .venv/* | node_modules/* | */node_modules/* | .bootstrap/*) continue ;;
  esac
  [[ "$path" =~ $secret_files_re ]] && note "  INFO ignored secret-looking file: $path"
done < <(git ls-files --others --ignored --exclude-standard)

note "== Result: $high HIGH, $review REVIEW =="
[[ "$high" -eq 0 ]] && exit 0 || exit 1
