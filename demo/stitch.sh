#!/bin/bash
# Join the Console film and the phone tour into one demo.
#
#   ./demo/stitch.sh
#
# Two recordings, deliberately made separately. The Console is driven by
# Playwright in a browser; the phone is `adb screenrecord` on an emulator.
# Nothing sensible records both at once, and faking a split screen by running
# them at different times and pretending otherwise would be the kind of small
# lie this project keeps not telling.
#
# So they are joined end to end with a card saying which is which. The phone
# is 1080x2400 and the Console is 1600x900, so the phone is scaled to the
# frame height and centred on a dark field rather than stretched.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$HERE/../recordings"
CONSOLE="${1:-$OUT_DIR/three-stories.webm}"
PHONE="${2:-$OUT_DIR/phone-tour.mp4}"
FINAL="$OUT_DIR/ekyatra-demo.mp4"

for file in "$CONSOLE" "$PHONE"; do
  [ -f "$file" ] || { echo "  missing: $file"; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# A card, so nobody has to guess that the camera has moved to a phone.
# Rendered as a web page rather than with ffmpeg's `drawtext`: this ffmpeg is
# built without libfreetype, and a page also gets the Console's own fonts.
( cd "$HERE" && node card.mjs "$WORK/card.png" \
    "And the same journey, on the family's phone" \
    "Tamil. Live against the same API." )
ffmpeg -v error -loop 1 -t 3 -i "$WORK/card.png" -r 25 -pix_fmt yuv420p "$WORK/card.mp4" -y

# Both parts to one codec, size and frame rate, or the concat demuxer refuses.
ffmpeg -v error -i "$CONSOLE" -r 25 -s 1600x900 -pix_fmt yuv420p -an "$WORK/a.mp4" -y
ffmpeg -v error -i "$PHONE" -r 25 -an \
  -vf "scale=-2:900,pad=1600:900:(ow-iw)/2:0:0x0b1220" -pix_fmt yuv420p "$WORK/b.mp4" -y

printf "file '%s'\nfile '%s'\nfile '%s'\n" "$WORK/a.mp4" "$WORK/card.mp4" "$WORK/b.mp4" > "$WORK/list"
ffmpeg -v error -f concat -safe 0 -i "$WORK/list" -c copy "$FINAL" -y

SECONDS_LONG=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$FINAL")
printf "  wrote %s\n  %.0fs, 1600x900\n" "$FINAL" "$SECONDS_LONG"
