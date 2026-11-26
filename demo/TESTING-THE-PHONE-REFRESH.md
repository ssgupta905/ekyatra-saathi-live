# For Ankshuk: testing the phone refresh fix

Branch `openemr-flow-end-to-end`, commit `eb42e6d`.

## The short version

The app now fetches on its own every 20 seconds while a family's screen is
open, regardless of events. Before, it fetched only when an event arrived
whose kind it recognised — and it did not recognise nine of them.

## What was wrong

The app holds no local database — no Room, no cache, nothing. It refreshes
when it is opened, and otherwise **only when an event arrives whose kind it
recognises**:

```kotlin
val revision =
    if (event.patientId == patientId && event.kind in PatientKinds) state.revision + 1
    else state.revision
```

`live.ts` had 21 kinds in that set. The Kotlin had 12. The nine missing ones
included `question.asked`, `request.raised` and `request.confirmed` — so a
family is asked a question and their phone does not know until it is closed
and opened again.

Your `131279f` fixed the web client's half of this. The Kotlin did not follow.

## Why the existing test did not catch it

`LiveTest` already had a case for exactly this — *"every kind the web treats
as a family's own is treated the same here"*. It held its own copy of the list
and asserted the Kotlin matched **that copy**, so it enforced whatever the list
had been the day it was written. The comment said it mirrored `live.ts`; the
code mirrored a transcript of it. It passed throughout.

It now reads `live.ts`. There is a second test on the web side that reads the
Kotlin, so the break shows up wherever you happen to be working.

One trap: Gradle does not know `live.ts` is an input, so it skipped the test as
up-to-date on precisely the change it exists to catch. `build.gradle.kts` now
declares it. If you ever see that test pass suspiciously fast after touching
`live.ts`, that is what to check.

## What to run

```bash
git pull
cd android
./gradlew testDebugUnitTest          # 54 tests
cd ../frontend && npm run test       # 78 tests
```

`-PapiBase` is **mandatory** for a build — `providers.gradleProperty("apiBase").get()`
has no default, so it fails outright without it:

```bash
cd android
./gradlew assembleDebug -PapiBase=https://ekyatra-saathi-ueoa.onrender.com/api
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Use that exact URL or the phone talks to a different backend from the Console.

## The test that actually matters

Tests passing proves the two lists match. It does not prove the screen
refreshes. **This is the part I could not do — the phone was unplugged before
I could watch it.**

1. Open the app on **EKY-KAMLA** or **EKY-SHANTI** and leave it open. Do not
   touch the screen.
2. Make the connector ask that family something. Either enter a Vacation in
   OpenEMR for a day they are booked (29 Nov hits both), or:
   ```bash
   curl -s -X POST https://ekyatra-saathi-ueoa.onrender.com/api/live/control \
     -H 'content-type: application/json' -d '{"action":"clear"}'
   ```
3. **Watch the screen without touching it.**

Before the fix: nothing happens until you close and reopen. After: the message
appears on its own — within a second or two if the stream is healthy, within
twenty if it is not, because the poll catches it either way.

Worth testing the stream being broken too, since that is the case the poll
exists for: put the phone in aeroplane mode for a minute with the screen open,
turn it off again, and the screen should catch up without being touched. That
exercises both the poll and the fetch-on-reconnect.

Worth also checking the Console in a browser at the same time — its half is
already live and verified in the shipped bundle, so the two should move
together.

## Two things that may bite you

**Your IP may have rotated.** The VM firewall admits one address at a time per
person, and mine changed twice in a day. If OpenEMR times out rather than
refusing, that is why:

```bash
gcloud compute firewall-rules update saathi-hms-ports \
  --source-ranges "$(curl -s https://api.ipify.org)/32,122.168.94.156/32,74.220.51.0/24,74.220.59.0/24"
```

`--source-ranges` **replaces** the list. Render's two `/24`s have to stay in it
or the hosted API stops reading the hospital — and that failure is quiet.

**OpenEMR has eight stacked Vacation rows on 29 Nov** from the filming takes.
Your `e194ecf` means they are now one leave rather than eight asks, so this is
cosmetic — but the calendar still looks silly on camera and the cleanup
command clears them.

One thing worth checking while you are in there: `e194ecf` changes the travel
date to "no earlier than one day before a booked visit". The film currently
captions Kamla's new plan as the one her own sentence produced. If the travel
date she now sees differs from what the film shows, the film is stale and I
should re-run it rather than let a caption describe an older answer.
