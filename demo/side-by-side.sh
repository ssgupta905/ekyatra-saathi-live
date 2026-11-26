#!/bin/bash
# Lay the Console and the phone side by side — two views of one run.
#
#   ./demo/side-by-side.sh
#
# Both inputs were recorded simultaneously by `connected.mjs`. This places
# them next to each other; it does not re-time either, and it does not trim
# one to match the other. Where the phone recording is shorter (its recorder
# has a three-minute ceiling) its last frame holds, which is honest — the
# phone was simply not recording any more, and freezing is visibly different
# from the phone having nothing to show.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../recordings"
BROWSER="${1:-$OUT/connected-browser.webm}"
PHONE="${2:-$OUT/connected-phone.mp4}"
FINAL="$OUT/ekyatra-connected.mp4"

for f in "$BROWSER" "$PHONE"; do
  [ -f "$f" ] || { echo "  missing: $f"; exit 1; }
done

# The phone is 1080x2400. Scaled to the browser's height it is ~450 wide,
# which leaves both legible at 1080p without either dominating.
ffmpeg -v error -y \
  -i "$BROWSER" -i "$PHONE" \
  -filter_complex "\
    [0:v]scale=1180:1000,setsar=1[left]; \
    [1:v]scale=-2:1000,setsar=1[right]; \
    [left][right]hstack=inputs=2,pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:0x0b1220[out]" \
  -map "[out]" -r 25 -pix_fmt yuv420p -preset medium "$FINAL"

read -r W H D < <(ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height -show_entries format=duration \
  -of csv=p=0:s=' ' "$FINAL" | tr '\n' ' ')
printf "  wrote %s\n  %sx%s · %.0fs\n" "$FINAL" "$W" "$H" "$D"
