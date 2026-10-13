#!/usr/bin/env bash
# Daily recount for restore-the-ada-mission.org
# usage: TRACKER_KEY=... pipeline/run.sh <professional-sheet download> <public-sheet download>
# The two arguments are the files the Google Drive connector saves when it downloads each
# response sheet. Nothing written here or printed contains a name or an email address.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(dirname "$HERE")
: "${TRACKER_KEY:?TRACKER_KEY must be set}"
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
python3 -I "$HERE/fetch.py" "$1" "$W/prof.csv"
python3 -I "$HERE/fetch.py" "$2" "$W/pub.csv"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in "$HERE/private.enc" -out "$W/bundle" -pass env:TRACKER_KEY
cd "$W"
python3 -I "$HERE/daily.py" prof.csv pub.csv --page "$REPO/index.html" --bundle bundle --write "${@:3}" \
  2>&1 | grep -v -e 'UserWarning' -e 'def H'
exit "${PIPESTATUS[0]}"
