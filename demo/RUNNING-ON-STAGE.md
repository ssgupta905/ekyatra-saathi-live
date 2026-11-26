# Running the demo on stage

Five terminals, about four minutes from cold. Everything below has been run
end to end on the machine this was built on; where something is fragile it
says so, and says what to do instead.

**The one-line version of what you are showing:** a hospital system nobody
modified publishes three completely different kinds of signal, Saathi reads
all three, asks the family what only the family knows, and a person approves
before anything moves.

---

## Before the day

```bash
make install                      # python + node deps
.venv/bin/pip install -e '.[openemr]'   # PyMySQL, for arrival times
```

You need Docker running, Node 22, and a JDK only if you want the Android app
(`brew install openjdk@17`).

---

## Terminal 1 — the hospital

```bash
cd demo/openemr && docker compose up -d
```

First boot takes two to three minutes while OpenEMR builds its schema. It is
ready when `http://localhost:8300` shows a login (**admin** / **pass**).

This is the stock `openemr/openemr:flex` image. Nothing of ours is inside it.
That is the claim the whole demo rests on, and it is worth saying out loud.

**Once, on a fresh database**, register EKYATRA as an API client:

```bash
PYTHONPATH=backend .venv/bin/python -m saathi.bootstrap.openemr_seed \
  --register --base-url http://localhost:8300 --key demo/openemr/openemr-key.pem
```

It prints a client id and key id. Put them in `demo/openemr/demo.env`. The key
file never leaves the machine and is git-ignored — a private key in a repo is
a private key in every clone.

---

## Terminal 2 — seed the cast

```bash
set -a; source .env; source demo/openemr/demo.env; set +a
make openemr-seed            # says what it would change, writes nothing
make openemr-seed-write      # does it
make stage-arrivals          # the clinic's morning, so "running late" is real
```

`openemr-seed` is safe to run as often as you like and is the fastest way to
see whether the connection works at all.

`stage-arrivals` writes arrival timestamps **relative to now**, so the clinic
is behind whenever you run the demo. Re-run it if the laptop has been asleep
for hours; it clears the day first, so it never stacks two mornings.

---

## Terminal 3 — the API

```bash
set -a; source .env; source demo/openemr/demo.env; set +a
.venv/bin/python -m uvicorn saathi.main:app --host 127.0.0.1 --port 8077 \
  --app-dir backend --timeout-graceful-shutdown 2
```

Check it in one line:

```bash
curl -s localhost:8077/api/health | python3 -m json.tool | grep -E 'actors|language'
```

Both must say `true`. If they say `false` the Groq key did not load, the
family's reply will not be read, and act four will not work.

Then the one precondition that fails **silently**:

```bash
curl -s localhost:8077/api/admin/policy/TMH-MUM | grep -o '"used_by_planner":[a-z]*'
```

Must say `true`. If it says `false`, the hospital has no saved rules — no
stated tolerance for how far a step may move, and no slot calendar to land
on. The planner then **refuses to search for dates at all**, which is
correct (it has been told nothing to search inside, and a date this system
invented is the one thing it must never offer a family) and looks like
nothing happening. Save them on **Configuration** first, or:

```bash
curl -s localhost:8077/api/admin/policy/TMH-MUM > /tmp/pol.json
# edit shift_tolerance_days for the steps you will move, then:
python3 -c "import json;print(json.dumps(json.load(open('/tmp/pol.json'))['policy']))" \
  | curl -s -X PUT localhost:8077/api/admin/policy/TMH-MUM \
      -H 'content-type: application/json' --data-binary @-
```

They save as **provisional** until a clinician confirms them, and the Console
says so on screen. Leave it that way — it is true.

### Getting back to "nobody has been asked yet"

```bash
curl -s -X POST localhost:8077/api/live/control \
  -H 'content-type: application/json' -d '{"action":"clear"}'
```

`clear`, **not** `reset`. `reset` rewinds the world and is refused outright
on real records (409), because it would delete patients, steps and plans
somebody entered. `clear` forgets what has been asked, read and searched,
and deletes nothing. Wait ~15s afterwards for the connector to re-read.

---

## Terminal 4 — the screens

```bash
cd frontend && SAATHI_API_PORT=8077 npm run dev
```

Control Centre on **http://localhost:5173**. Pick **Seema Kamble** (navigator).

**`SAATHI_API_PORT=8077` is not optional.** The dev proxy defaults to port
8000, and if anything else is listening there the Console will reach it
instead — showing a "DEMO WORLD" badge and `GET /requests/waiting failed:
500`, which looks exactly like our code being broken. It cost one take to
find. Plain `make web` is only correct when the API is on 8000.

---

## Terminal 5 — the phone (optional)

```bash
make emulator                                          # or open an AVD in Android Studio
cd android && ./gradlew :app:assembleDebug -PapiBase=http://10.0.2.2:8077/api
~/Library/Android/sdk/platform-tools/adb install -r \
  android/app/build/outputs/apk/debug/app-debug.apk
~/Library/Android/sdk/platform-tools/adb shell am start -n org.ekyatra.saathi/.MainActivity
```

`10.0.2.2` is how the emulator reaches this Mac. On a physical phone use the
Mac's LAN address and start uvicorn with `--host 0.0.0.0`.

If the emulator shows "System UI isn't responding" on first boot, tap **Wait**
— that is the emulator, not the app.

---

## The three beats, and who presses what

### One — the doctor is away

**You do this, in OpenEMR, on camera.** Calendar → the **+** button → the
**Provider** tab → category **Vacation** → all day → 27 November → Save.

Then show the day: the Vacation band appears across the top and **the
patient's 11:30 appointment is untouched**. That is the whole point — nothing
in the appointment feed changed, so nothing watching appointments could see
this.

Within three seconds, in the Console:

- **Hospitals right now** — the connector's counts move (`leave`,
  `leave:collision`).
- **Approvals → Asked, and no answer yet** — the question Saathi sent, in the
  family's own language and script.

Saathi asks rather than assumes, because who can travel and what it costs are
not in any hospital record.

### Two — she answers

On the phone, or with one command:

```bash
curl -s -X POST localhost:8077/api/live/inject -H 'content-type: application/json' \
  -d '{"patient_id":"EKY-SHANTI","text":"Amar sathe ami jabo. Trainer tickets 900 taka hobe. 1 tarikher age noy, salary tokhon ase."}'
```

In **Approvals → What families have asked for**:

- her sentence, verbatim, in her own script;
- the reading: *asks to move a visit — not before 01 Dec*;
- *2 coming with them · they said about ₹900 · in their words: "…"*

**The line to say out loud:** that ₹900 is there because *she* said it, with
the sentence it came from. Saathi never proposes a fare — there is no fare
source behind this system, and an invented number would read to a family as
the hospital's own estimate. A figure that cannot be traced to the family is
dropped before it reaches this screen.

### Two and a half — the same signal, a different answer

Kamla's creatinine is still open and her visit is near. Saathi asks about her
travel; she replies that the night bus cost ₹1,400 and the money is gone.

**That one sentence turns the decision over.** Moving her visit would spend
her ₹1,400 twice, so EKYATRA keeps the date and asks the hospital to bring the
report forward instead — written into OpenEMR's own record as a FHIR `Task`.
Say the same scenario with a *refundable* ticket and watch it ask about dates
instead; that is the contrast worth inviting a judge to try.

The honest caveat: OpenEMR does not display `Task`s in its UI, so the request
is auditable and queryable but a clerk would not see it there.

### Three — a person decides

Click **Agree, and re-plan**. Only now does the planner see it.

If the reading is wrong, **This is not what they said** records the correction
and changes no plan. Invite a judge to try it — it is the honest half of
running a language model in a loop like this.

Then open a family and look at **How this was worked out**: every line was
published by the code that did the work, carrying the time it actually took.
`[GUARD]` lines are refusals and are never filtered out.

Underneath it, **What the planner considered** — every date tried and the rule
that killed each one. This fills only after somebody agrees a reading: the
planner searches against the family's constraint at that moment, not before,
because there is nothing to search against until a person has confirmed what
she meant. A family asking for a date outside the hospital's stated tolerance
is the one worth showing — it is ruled out by name, and the date offered
instead is the closest the rules allow.

### Four — what goes back to research

A doctor's or administrator's screen, not the navigator's: **Research
contribution**. Sign in as Dr R. Menon.

It will show **0 rows** until a family consents, and that is the honest
starting point. To ask and answer on camera, from a terminal:

```bash
P=EKY-SHANTI
REQ=$(curl -s -X POST localhost:8077/api/patients/$P/consent/requests \
  -H 'content-type: application/json' -d '{
   "purpose":"research","requester_id":"NCG-IN",
   "requester_name":"National Cancer Grid (NCG), India",
   "categories":["travel_burden"],
   "reason":"Travel and cost burden, de-identified"}' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
curl -s -X POST localhost:8077/api/patients/$P/consent/requests/$REQ/grant \
  -H 'content-type: application/json' \
  -d '{"granted_by":"Shanti Kumari","capacity":"self","channel":"ivr"}'
```

Refresh the screen: **1 row, 3 withheld — no research consent**. The withheld
count is the point. A file of one row from a cohort of four is a different
claim from one row out of one, and a reader who cannot tell will assume the
flattering one.

Revoking works too (`/consent/grants/{id}/revoke`) and the row disappears —
worth offering if a judge asks whether consent is real.

### And the other two signals

- **A pending report.** `ServiceRequest` status moves without its
  `_lastUpdated` moving, so a cursor poller would never see it. Snapshots are
  compared instead. Mark a report `prelim` in OpenEMR's orders UI to show it.
- **A clinic running late.** Nobody records that a clinic is behind — there is
  no such field. The figure is derived from arrival timestamps an ordinary
  calendar save leaves behind. Change one arrival time in the database and the
  number moves.

---

## If a judge asks to try something

They should. Four things are generic rather than scripted:

| They do | What happens |
|---|---|
| Cancel or move any appointment | Snapshot diff catches it |
| Mark any provider away, any day | Read by category, not by name or date |
| Mark any order pending or complete | Snapshot diff over all open orders |
| Mark patients arrived | The delay is re-derived from the log |

Anything outside those four produces **"we could not read this"**, never a
guess. That is deliberate and there is precedent for it everywhere in the
codebase: an unreadable appointment status becomes `entered-in-error` rather
than a plausible one, speech that failed returns nothing rather than an empty
transcript, and a message the guard cannot validate is sent to a person
instead of to the family.

---

## When something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| The board never changes | **The commonest failure by far.** The hospital id in `SAATHI_HOSPITAL_SYSTEMS` does not match the one the cast carries, so the connector matches nobody and says nothing. | The seeder writes the cast at `TMH-MUM`. Use that exact id. |
| `actors: false` in health | The Groq key did not load | `source .env` before starting uvicorn |
| Questions come out in the wrong language | The family's language is a record, not a view setting | `PATCH /api/patients/{id}/language` |
| "running about 0 min behind" | The staged morning is from another day, or the laptop slept | `make stage-arrivals` again |
| Leave is entered and nothing happens | It is already in `_seen_leave` from an earlier run | Restart the API; a connector only acts on a leave once |
| `401` on everything | Sign-in is on | `SAATHI_AUTH=off` is in `demo.env`; make sure it is sourced |
| A family's reply reads as empty, or a figure goes missing | **Groq's free tier is 8,000 tokens a minute.** Several readings at once — one leave affecting three families — will 429. The actor retries once after the wait the API asks for, then gives the message to a person. | Space out injections by ~10s when rehearsing, or move the key to a paid tier before the day. Measured: sequential extraction is 5/5 on both stories; six concurrent calls 429 reliably. |
| No arrival times at all | PyMySQL missing, or port 3307 not published | `pip install -e '.[openemr]'`, and use `demo/openemr/docker-compose.yml` |

The Console reporting **arrival with no delay** is not a bug. It is what the
system does when nothing can tell it how late the clinic is, and a guessed
delay would be worse than none — a family rearranges their day around it.

---

## The family's phone

The four tabs are **இன்று / Today**, **திட்டம் / Plan**, **செய்திகள் / Messages**
and **செலவு / Spends**. Two of them are worth showing deliberately:

- **Plan → Near you.** Real pharmacies, labs and medical suppliers around the
  hospital, with distances and opening hours. Read from our own table in
  milliseconds, not from a public server that takes thirty seconds — see
  `docs/handoff-routes-places-map.md`. Reload it with
  `python -m saathi.tools.load_places FILE --write`.
- **Spends.** When nothing has been recorded yet it says *"cannot say right
  now: no previous journey spend recorded"* rather than showing a number.
  That is the rule, not an empty state waiting to be filled.

`./demo/phone-tour.sh` drives all four and records them to
`recordings/phone-tour.mp4`.

**What the emulator has not proved**, and should not be claimed: the Maps
hand-off, the location-permission flow, a real GPS fix, dialling from a place
card, and the Kharcha add/pay forms. All five need a handset. Everything else
on the phone has been verified.

## Re-recording the film

```bash
make demo-stories
```

It checks every prerequisite first and refuses to record if any is missing,
rather than producing a take with a caption that is not true. It clears any
leftover leave so act one is genuinely the first time, and it verifies the
calendar is on the right day and that ₹900 reached the record **before** it
says either thing on screen. Two earlier films shipped false captions; this
one stops instead.

Output: `recordings/three-stories.webm`. `make demo-mov` converts the newest
recording to a QuickTime `.mov` in `~/Documents`.

For the full thing — Console and phone in one file:

```bash
make demo-stories        # the Console, two hospital stories
./demo/phone-tour.sh     # the phone, four tabs in Tamil
./demo/stitch.sh         # joins them -> recordings/ekyatra-demo.mp4
```

They are recorded separately because nothing sensible records a browser and an
emulator at once, and a faked split screen would be the one small lie this
project keeps not telling. The join puts a card between them saying so.

---

## What to say about the limits

Say these before a judge finds them. They are all in `docs/openemr.md`.

- OpenEMR does not display FHIR `Task`s in its UI, so the approval record is
  auditable but a clerk would not see it there.
- `DiagnosticReport.status` always reads `final` from OpenEMR whatever the
  underlying report says, and the clinician's sign-off is not in FHIR at all.
- A leave's end date and the arrival clock are read from the database, because
  OpenEMR does not project either. The database connection is `SELECT`-only,
  enforced three ways: every SQL string in the module is a `SELECT` (a test
  parses the module and fails otherwise), the session is opened read-only, and
  the account has only `SELECT` granted.
- Multi-day leave reads as one day, because that is all OpenEMR sends.
