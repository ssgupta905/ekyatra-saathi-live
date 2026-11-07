#!/bin/bash
# Record the emulator's screen.
#
#   ./record-phone.sh 13-meena-sarvam-readaloud 170
#
# `adb shell screenrecord` writes an mp4 on the device and we pull it, which
# needs nothing installed on the Mac — no ffmpeg, no screen capture permission,
# and no window to keep in the foreground. Its ceiling is three minutes per
# clip, which is why the clips are short and named for what they show.
set -euo pipefail

NAME="${1:?usage: record-phone.sh <name> [seconds]}"
SECONDS_LIMIT="${2:-170}"
OUT="${SAATHI_CLIPS_DIR:-$HOME/Downloads/demo-recordings}"
ADB="${ANDROID_HOME:-$HOME/Library/Android/sdk}/platform-tools/adb"

mkdir -p "$OUT"
"$ADB" wait-for-device
echo "recording $NAME for up to ${SECONDS_LIMIT}s — drive the app now"
"$ADB" shell screenrecord --time-limit "$SECONDS_LIMIT" --bit-rate 6000000 \
  /sdcard/saathi-clip.mp4
"$ADB" pull /sdcard/saathi-clip.mp4 "$OUT/$NAME.mp4" >/dev/null
"$ADB" shell rm -f /sdcard/saathi-clip.mp4
ls -lh "$OUT/$NAME.mp4"
