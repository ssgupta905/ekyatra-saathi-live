# What changed on `openemr-flow-end-to-end` — 27 Nov

Pushed `4340dcd..08b6c33`. The API on Render has auto-deployed it and I verified
the fix against the live deployment, not just locally.

**Take a pull.** Only ~72 lines are backend; the rest is the film rig and docs.

---

## 1. The one that matters: the planner could book a family onto the doctor's leave day

It did, on camera. A family said "not before the 1st", the doctor was away on
the 1st, and the planner offered the 1st and wrote it into OpenEMR.

**Why.** `_act_on_leave` remembers a signal and asks the family, and stops — it
never calls `raise_disruption`. So the leave never becomes a `Disruption`,
`world.open_disruptions()` doesn't contain it, and the planner's
`ResourceCalendar` has nothing to refuse. Even if it had, `first_free_date`
matches on `resource_id`, and a step booked against no named resource is free
immediately — so a provider's absence could not have blocked it anyway.

**Fix** (3 files, 32 lines):

- `hospital_sync.py` — new `away_days: set[date]` field, filled with the days
  each published leave covers, cleared on reset.
- `runner.py` — `replan_for_request` passes `days_away=` into the search.
- `planner/options.py` — `candidates_for_request` takes `days_away` and refuses
  those dates under `Verdict.RESOURCE_DOWN`, **recorded** via `note()` rather
  than skipped, so the Console shows why.

Verified live on the deployment, same input before and after:

```
before:  01 Dec — offered
after:   01 Dec — rejected: the resource is still down that day
                  (the clinician is away that day)
         08 Dec — offered
```

Pinned by `test_a_day_the_clinician_is_away_is_never_offered_back`. I checked it
actually fails with the fix disabled. Suite: 1179 passing, `ruff check` clean.

**Open question for you**: the proper fix is probably to raise a real
`STAFF_UNAVAILABLE` disruption on a leave collision. I didn't, because it
cascades into options/approvals/holding alongside the existing ask-the-family
path and I didn't want to touch that days before the finale. Your call whether
to do it properly after.

**Cosmetic**: `WHY[Verdict.RESOURCE_DOWN]` reads "the resource is still down
that day", which is a bit mechanical about a human. The detail string carries
the readable version.

---

## 2. Two things that will bite you on stage

- **Clear the leave between runs.** Every run writes a `Vacation` into OpenEMR,
  and a *second* leave for the same provider on the same day is not news to the
  connector — so nobody gets asked and it looks broken. This cost me four takes
  before I understood it. Command is in `demo/openemr/gcp/STAGE-SETUP.md`; the
  film now checks OpenEMR's day view first and refuses with the command printed.

- **Ask judges to cancel, not delete.** `AppointmentSnapshot.diff()` only walks
  what the hospital returns, so a deleted row has nothing to compare against. A
  status change to Canceled is caught; a deleted appointment is invisible.

---

## 3. `STAGE-SETUP.md` corrections

- It told you to export `CLOUDSDK_CONFIG=~/.config/gcloud-saathi`. **That profile
  has no credentialed account** — every command fails with "You do not currently
  have an active account selected", which reads like being logged out rather than
  the wrong profile. The account is in the default profile.
- Added how to get the VM's OpenEMR admin password into `.env` as
  `SAATHI_OPENEMR_PASS` without putting it on screen. It survives a reboot but
  not a VM rebuild. `admin`/`pass` in `docker-compose.yml` is the **local**
  instance's and will not work on the VM.

---

## 4. Film rig (`demo/hosted-flow.mjs`) — ignore unless you run it

New beats: the approval, the write-back into OpenEMR, its own calendar, the
loop closing via `arrive_by_source: hospital_booking`, the un-cancelled slot,
stay/rail/stated-fare.

Eleven fixes, all mine, all the rig rather than the system: hardcoded Devanagari
checked against a Bengali screen; a family below the fold in a 32-family picker;
the Why drawer overlaying the approvals queue; the queue labelled by patient id
not name; `am start` resuming wherever the app was left; a notification shade I
pulled myself; the 300s idle lock eating a third of a take; an ISO date where
PostCalendar wants YYYYMMDD; and the capture device hardcoded to index `2` —
an iPhone in Continuity Camera range shifts "Capture screen 0" to 4, so one
whole take recorded the Desk View camera. It's resolved by name now.

---

## 5. Still open, yours to call

- **`Translations.kt` has two sources of truth.** `make android-strings` deleted
  144 lines / 24 hand-written strings and broke the build (714d6b8, restored in
  5d79b8d). I have not run it again and would not until that's resolved.
- **The phone auto-refresh** (20s poll + refresh-on-reconnect) still needs a real
  device watched unattended. I've never seen a physical screen refresh on its own.
