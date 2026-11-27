# Demo runbook — re-runnable from cold

Every step is a command you can paste. **Step 0 resets everything**, so the
whole thing can be run again without hunting for what last time left behind.

Written so somebody can say "do step 4" and get exactly one thing done.

---

## Preconditions (check once per machine)

```bash
# 1 · the three deployed services answer
curl -s -o /dev/null -w 'api %{http_code}\n'      https://ekyatra-saathi-ueoa.onrender.com/api/health
curl -s -o /dev/null -w 'console %{http_code}\n'  https://ekyatra-saathi-control-centre.onrender.com
curl -s -o /dev/null -w 'openemr %{http_code}\n'  http://8.231.81.219:8300/interface/login/login.php?site=default

# 2 · the phone/emulator is attached and the app is installed
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"; adb devices

# 3 · the APK points at the DEPLOYMENT, not localhost.  If in doubt, rebuild:
cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
  ./gradlew :app:assembleDebug -PapiBase=https://ekyatra-saathi-ueoa.onrender.com/api \
  && adb install -r app/build/outputs/apk/debug/app-debug.apk

# 4 · secrets the film needs, in .env (never on screen — see step 9)
grep -c 'SAATHI_OPENEMR_PASS\|GROQ_API_KEY\|SARVAM_KEY' .env   # expect 3
```

**The Makefile's Android targets do not work on this machine.** `make` uses
`/usr/libexec/java_home -v 17`, which does not see the Homebrew JDK. Use the
explicit `JAVA_HOME` above.

**Your egress IP must be in the VM firewall.** It is a NAT pool, so a `/32`
will not hold:

```bash
export PATH=/opt/homebrew/share/google-cloud-sdk/bin:$PATH
gcloud compute firewall-rules update saathi-hms-ports \
  --source-ranges "$(curl -s https://api.ipify.org | cut -d. -f1-3).0/24,74.220.51.0/24,74.220.59.0/24"
```

Note `gcloud` uses the **default** profile. `CLOUDSDK_CONFIG=~/.config/gcloud-saathi`
has no credentialed account despite what STAGE-SETUP.md says.

---

## Step 0 · Reset (run this before every take)

Two halves. Both are needed; skipping the first is what cost four takes.

```bash
cd ~/Documents/EKYATRA

# a · remove every leave previous takes wrote into OpenEMR.
#     A SECOND leave for the same provider on the same day is NOT NEWS to the
#     connector, so nobody gets asked and the take dies four minutes in.
export PATH=/opt/homebrew/share/google-cloud-sdk/bin:$PATH
gcloud compute ssh saathi-hms --zone asia-south1-c --quiet --command \
"sudo docker exec -i openemr-mysql-1 mariadb -uroot -proot openemr -N -B -e \
\"DELETE FROM openemr_postcalendar_events WHERE pc_eventDate BETWEEN '2026-11-27' AND '2027-02-28' AND (pc_pid IS NULL OR pc_pid=0); SELECT ROW_COUNT();\""

# b · forget the working state (questions, readings, options). Deletes nothing.
.venv/bin/python -c "import httpx; print(httpx.post('https://ekyatra-saathi-ueoa.onrender.com/api/live/control', json={'action':'clear'}, timeout=240).status_code)"
```

Verify — all three must be `0`, and leaves must be `none`:

```bash
.venv/bin/python -c "
import httpx; A='https://ekyatra-saathi-ueoa.onrender.com/api'
for p in ('/questions/waiting','/requests/waiting','/disruptions/pending'):
    print(p, len(httpx.get(A+p, timeout=60).json()))"
```

---

## Step 1 · Pick the day

The leave must land on a day that has appointments **and no existing leave**.

```bash
cd ~/Documents/EKYATRA && PYTHONPATH=backend .venv/bin/python - <<'PY'
from saathi.bootstrap.openemr_seed import _token
import collections, httpx
base = "http://8.231.81.219:8300"
tok = _token(base, "GYV40iM_r9VKvMsKtd0VU6fWOeRF-5W-X52OCR4LPQc",
             "d05c16c1640742ea83d7a013a70374b8", "demo/openemr/openemr-key-vm.pem")
r = httpx.get(f"{base}/apis/default/fhir/Appointment",
              params={"date": ["ge2026-11-27", "le2027-02-28"], "_count": 80},
              headers={"Authorization": f"Bearer {tok}"}, timeout=60)
appts, leaves = collections.Counter(), set()
for e in (r.json().get("entry") or []):
    a = e["resource"]; d = str(a.get("start"))[:10]
    if any("Patient/" in str(p.get("actor",{}).get("reference","")) for p in a.get("participant", [])):
        appts[d] += 1
    else: leaves.add(d)
print("leaves:", sorted(leaves) or "none")
print("usable:", [(d,n) for d,n in sorted(appts.items()) if d not in leaves and n>=2])
PY
```

Pick the day with the most families. **29 November has three** — the richest.

---

## Step 2 · Record

```bash
cd ~/Documents/EKYATRA
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
export SAATHI_API_URL=https://ekyatra-saathi-ueoa.onrender.com
export SAATHI_PANEL_URL=https://ekyatra-saathi-control-centre.onrender.com
export SAATHI_OPENEMR_URL=http://8.231.81.219:8300
export SAATHI_LEAVE_DAY=2026-11-29          # from step 1

caffeinate -disu -t 2400 &                  # -u is what stops the 300s lock
caffeinate -dis node demo/hosted-flow.mjs
```

**Rules while it runs** — each learned the hard way:

- **Nobody touches the machine, including me.** Editing a file brings the IDE
  forward and it lands in the film. One take captured `.env` with four live
  API keys legible on screen.
- `caffeinate -d` alone is not enough. Without `-u` the screen locks after 300
  seconds and a third of the film is the lock screen — which passes the
  brightness check, because a wallpaper is a picture.
- Do not pull down the notification shade. The film force-stops the app and
  presses HOME first, but a shade pulled mid-take covers everything.

---

## Step 3 · Verify before believing it

The brightness check only proves there *is* a picture, not the right one.

```bash
cd ~/Documents/EKYATRA
ffprobe -v error -show_entries format=duration -of csv=p=0 recordings/hosted-flow.mp4
ffmpeg -hide_banner -i recordings/hosted-flow.mp4 -af volumedetect -f null - 2>&1 | grep max_volume
# must be under 0 dB; a positive figure means the mix clipped

# sample frames and LOOK at them — for the lock screen, the webcam, the editor
for t in 60 240 420 600 780; do
  ffmpeg -v error -ss $t -i recordings/hosted-flow.mp4 -frames:v 1 -vf scale=800:-1 /tmp/f$t.png -y
done
open /tmp/f*.png
```

Check specifically:
- no macOS lock screen
- no VS Code / terminal (and **never** `.env`)
- the picture is the screen, not the Desk View camera — an iPhone in
  Continuity range shifts `Capture screen 0` from index 2 to 4. The film
  resolves it by name, but confirm.

```bash
cp recordings/hosted-flow.mp4 ~/Documents/EKYATRA-demo-$(date +%H%M).mp4
```

---

## Step 4 · What each beat should show

| Beat | Expect |
|---|---|
| `[event]` | OpenEMR's own calendar, `VACATION oncology leave` saved |
| `[asked]` | every affected family, each in their own language |
| `[board]` | one change, all families, grouped by event |
| `[board]` | a row opened — agent trace and refusals inline |
| `[reply]` `[read]` | romanised reply → constraint, with the sentence kept |
| `[human]` | a person agreeing before the planner may act |
| `[plan]` | **every date tried and the rule that refused it** |
| `[talk]` | Saathi's proposal on the family's phone |
| `[money]` | the folded card, tapped open, each line saying whose number |
| `[write]` | the booking in OpenEMR, then `arrive_by_source: hospital_booking` |
| `[guard]` | the old slot it refuses to pretend it cancelled |
| `[voice]` | Sarvam audio, verified not the phone's own TTS |
| `[stay]` `[book]` | dharamshala first; station codes, no train number |
| `[research]` | consent granted, 1 row released, the rest withheld |

A missing beat is reported in the log, not hidden. `no reading for …` and
`dropped the … clip` are honest outcomes, not failures.

---

## Step 5 · If a take fails

| Message | Cause | Fix |
|---|---|---|
| `offers no Vacation category (saw: )` | not logged into OpenEMR | `SAATHI_OPENEMR_PASS` missing from `.env` |
| `already holds a leave on …` | step 0a skipped | run step 0a |
| `the connector noticing the leave … did not happen` | a leave already existed on that day | step 0a, then pick a clean day |
| `the family list is not on the phone` | notification shade, or app resumed mid-screen | film handles it; if it recurs, `adb shell input keyevent KEYCODE_HOME` |
| `could not reach the approval button` | the Why drawer is covering the queue | film presses Escape; check the Console deployed |
| `nothing on the phone reads "…"` | wrong language, or the target is above the fold | film searches both ways and reads language from the question |
| black / dim picture | display locked, or the wrong capture device | `caffeinate -disu`; check `Capture screen 0` index |

---

## Step 6 · Deploy a code change first

The film drives the **deployment**, not your working tree.

```bash
git checkout openemr-flow-end-to-end && git merge <branch> && git push origin openemr-flow-end-to-end
```

Render auto-deploys and swaps without an outage you can poll for, so verify
**behaviourally** — the deploy is live when the system gives a different
answer, not when a dashboard says so.

---

## Step 7 · The leftovers a take creates

- One `VACATION oncology leave` in OpenEMR → removed by step 0a.
- Real bookings from approvals, which stay. They are legitimate records the
  system wrote and they make later takes richer.
- Questions, readings and option sets → cleared by step 0b.

---

## Step 8 · Known-failing, do not be alarmed

`packages/i18n/src/android.test.ts` fails — 1 failed / 77 passed — and failed
before any of this work. `Translations.kt` has two authors and
`make android-strings` deletes the hand-written half (`5d79b8d`). **Do not run
it to make the test pass**; it will break the Android build.

---

## Step 8b · Rendering the produced film

```bash
cd demo && CHROME=$(node -e "const {chromium}=require('playwright');console.log(chromium.executablePath())")
cd film && npx remotion render Demo ../../recordings/EKYATRA-demo.mp4 \
  --browser-executable="$CHROME" --concurrency=2 --timeout=120000
```

**`--browser-executable` is not optional on this machine.** Remotion's bundled
`chrome-headless-shell` never mounts the root component, and the only symptom
is:

```
A delayRender() "Waiting for root component to load" was called
but not cleared after 28000ms
```

which points at your composition and is wrong. It is not React 18 vs 19, not
the Node version, and not a JSON import — all of which look plausible and cost
an hour between them. The proof is that the same bundle loads with **zero**
console errors in Playwright's Chromium: serve `remotion bundle --out-dir` over
a static server and open it with Playwright to see for yourself.

Worse, a failed render **exits 0 and leaves the previous output file in place**,
so the duration looks unchanged rather than wrong. Always check:

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 recordings/EKYATRA-demo.mp4
# compare against:  npx remotion compositions --browser-executable="$CHROME"
```

Do not install another Node to chase this. `brew install node@22` upgrades
`simdjson`, which the installed Node links against, and breaks `node` outright
until `brew reinstall node`.

Rebuilding the film after a change:

| changed | run |
|---|---|
| one clip | `node demo/clips.mjs --only NN`, then `node demo/stage-clips.mjs` |
| the wording | edit `demo/film/src/script.json`, then `.venv/bin/python demo/narrate.py` |
| a drawn scene | nothing; just re-render |
| the voice | `NARRATOR=sarvam .venv/bin/python demo/narrate.py` |

Narration drives the length: each section lasts its spoken line plus a breath,
so rewording re-times the film automatically.

---

## Step 9 · Before sending the film anywhere

1. Scrub for secrets — step 3's frame check, looking specifically for `.env`.
2. `EKYATRA-full-demo.mp4` (27 Nov, 18:10) **contains live API keys** for
   Groq, Sarvam, Render and OpenEMR, from 3:25 to ~4:25. Do not distribute.
   Rotate those four and delete the file.
