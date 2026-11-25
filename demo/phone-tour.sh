#!/bin/bash
# Record the family's phone: the four tabs, in Tamil, against the live API.
#
#   ./demo/phone-tour.sh            # writes recordings/phone-tour.mp4
#
# `adb shell screenrecord` writes an mp4 on the device and we pull it, which
# needs nothing installed on the Mac — no ffmpeg for capture, no screen
# recording permission, and no window to keep in the foreground.
#
# The taps are coordinates, which is brittle and deliberately so: driving this
# through a UI-automation framework would mean a second description of the app
# to keep in step with the first. A tour that lands on the wrong tab is
# obvious in the first frame; a test harness that drifts is not.
#
# Coordinates are for a 1080x2400 emulator. `adb shell wm size` to check.
set -euo pipefail

ADB="${ANDROID_HOME:-$HOME/Library/Android/sdk}/platform-tools/adb"
OUT="${1:-recordings/phone-tour.mp4}"
PKG=org.ekyatra.saathi

# Which family. The Tamil one, because Tamil is the language this project
# added last and the one most likely to be missing a string somewhere.
FAMILY_Y=1054      # EKY-RAMESH in the family list
TAB_Y=2226
TAB_TODAY=150
TAB_PLAN=408
TAB_MESSAGES=670
TAB_SPENDS=934

tap() { "$ADB" shell input tap "$1" "$2"; sleep "${3:-4}"; }
swipe() { "$ADB" shell input swipe 540 "$1" 540 "$2" 700; sleep "${3:-3}"; }

"$ADB" wait-for-device
"$ADB" shell am force-stop "$PKG"
"$ADB" shell am start -n "$PKG/.MainActivity" >/dev/null
sleep 6

echo "  recording — do not touch the emulator window"
"$ADB" shell screenrecord --time-limit 100 --bit-rate 8000000 /sdcard/tour.mp4 &
RECORDER=$!
sleep 3

# The families, with their languages shown as endonyms.
sleep 3
tap 210 "$FAMILY_Y" 7

# Today: the plan, in Tamil, read aloud by the service voice.
sleep 4
swipe 1500 900 3

# Plan: how to get there, and what is near the hospital.
tap "$TAB_PLAN" "$TAB_Y" 7
swipe 1700 600 4
swipe 1500 700 4

# Spends: this month and next, and the honest "cannot say yet".
tap "$TAB_SPENDS" "$TAB_Y" 7
swipe 1500 800 4

# Messages: what Saathi asked and what they replied.
tap "$TAB_MESSAGES" "$TAB_Y" 7
swipe 1400 800 3

wait "$RECORDER" 2>/dev/null || true
sleep 3
mkdir -p "$(dirname "$OUT")"
"$ADB" pull /sdcard/tour.mp4 "$OUT" >/dev/null
"$ADB" shell rm /sdcard/tour.mp4
echo "  wrote $OUT"
