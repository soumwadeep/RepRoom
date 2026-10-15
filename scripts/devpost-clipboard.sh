#!/usr/bin/env bash
# Walk the Devpost submission form one field at a time, copying each answer to
# the clipboard so nothing has to be typed.
#
#   scripts/devpost-clipboard.sh              # start at the first field
#   scripts/devpost-clipboard.sh --from 07    # resume at field 7
#   scripts/devpost-clipboard.sh --list       # just show the order
#
# Each pass: press Enter to copy, click the box in Devpost, press Cmd+V, then
# Enter again for the next field. It overwrites your clipboard every time -- if
# you have something in there you care about, put it somewhere first.
#
# The canonical text of every answer is docs/devpost/*.txt. Edit those, not this
# script, and the two can never disagree.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DIR="$ROOT/docs/devpost"

FROM=""
LIST_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --list) LIST_ONLY=1; shift ;;
    -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -d "$DIR" ]]; then
  echo "no field files at $DIR" >&2
  exit 1
fi

# bash 3.2 ships with macOS and has no mapfile, so the file list is built the
# long way round.
FILES=()
while IFS= read -r line; do FILES+=("$line"); done < <(ls "$DIR"/*.txt | sort)

label_of() {
  local base; base="$(basename "$1" .txt)"
  local rest="${base#*-}"
  rest="${rest//-/ }"
  printf '%s\n' "$rest" | awk '{ print toupper(substr($0,1,1)) substr($0,2) }'
}

TOTAL=${#FILES[@]}
INDEX=0
for f in "${FILES[@]}"; do
  INDEX=$((INDEX + 1))
  num="$(basename "$f" .txt)"; num="${num%%-*}"
  if [[ -n "$FROM" && "$num" < "$FROM" ]]; then continue; fi
  label="$(label_of "$f")"
  lines=$(wc -l < "$f" | tr -d ' ')
  words=$(wc -w < "$f" | tr -d ' ')

  if [[ "$LIST_ONLY" == "1" ]]; then
    printf '  %s  %-28s %s words\n' "$num" "$label" "$words"
    continue
  fi

  echo
  printf '\033[1m[%s/%s] %s\033[0m  (%s words)\n' "$INDEX" "$TOTAL" "$label" "$words"
  if grep -q "PASTE-\|<< \|TODO" "$f"; then
    printf '\033[33m  this one still contains a placeholder -- fill it in docs/devpost/%s before pasting\033[0m\n' "$(basename "$f")"
  fi
  read -r -p "  Enter to copy, then Cmd+V into the Devpost box... " _
  pbcopy < "$f"
  printf '\033[32m  copied %s.\033[0m paste it, then Enter for the next field.\n' "$label"
  read -r -p "  " _
done

if [[ "$LIST_ONLY" == "1" ]]; then exit 0; fi

echo
echo "All fields copied. Two things left that are not text boxes:"
echo "  * attach docs/friction-log.md   -- worth up to a 10% judging bonus"
echo "  * attach docs/feature-requests.md"
echo
echo "And one thing to check before you press Submit: the entry URL still reads"
echo "'jio-tv-plus'. If that is this project's entry, rename it to RepRoom; if it"
echo "is a different idea, start a new submission instead of overwriting it."
