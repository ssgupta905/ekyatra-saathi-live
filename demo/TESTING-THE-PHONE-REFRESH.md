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

## Setup on your machine

Nothing new is needed for the backend or the web — `e194ecf` made the tests
stop reading your `.env`, so they are self-contained. The Android side has
four requirements and none of them are in the repo:

1. **`local.properties`** — gitignored, so it is not in your checkout. One
   line, pointing at your own SDK:
   ```
   sdk.dir=/Users/<you>/Library/Android/sdk
   ```
   Opening the `android/` folder once in Android Studio writes it for you.

2. **JDK 17.** The build sets source and target compatibility to 17. Android
   Studio's bundled JBR will do. There is no `java` on PATH on this machine,
   so I build with:
   ```bash
   export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
   ```

3. **Android SDK Platform 37.** `compileSdk = 37`, which is recent enough that
   you may not have it. SDK Manager → SDK Platforms → Android SDK Platform 37.
   This is the one most likely to stop you, and the error names it clearly.

4. **A device.** Developer options on, USB debugging accepted, and the phone
   unlocked when you plug it in — the authorisation prompt does not appear on
   a locked screen. `adb devices` showing `unauthorized` means the prompt is
   waiting on the handset.

Gradle itself needs nothing: the wrapper fetches 9.8.2 on first run.

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
2. Make the connector ask that family something. This needs no VM access and
   no firewall — it is a public URL:
   ```bash
   curl -s -X POST https://ekyatra-saathi-ueoa.onrender.com/api/live/control \
     -H 'content-type: application/json' -d '{"action":"clear"}'
   ```
   (Entering a Vacation by hand in OpenEMR's calendar does the same thing and
   looks better on camera, but that is the one path that needs your IP on the
   firewall.)
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

**You do not need the VM firewall to test the app.** Worth being clear, because
an earlier draft of this document implied otherwise. Three separate paths:

| Who talks to what | Needs an allow-list? |
|---|---|
| Phone → deployed API | **No.** A public Render URL, reachable from any network. |
| Deployed API → OpenEMR on the VM | **No, already done.** Render's egress ranges are allow-listed permanently; they do not rotate. |
| You → OpenEMR's web UI in a browser | **Yes** — and only this. |

So the test below needs nothing but the internet. Trigger the ask with
`/api/live/control` and watch the phone. The firewall only matters if you want
to enter a leave by hand in OpenEMR's own calendar, which is a nicer thing to
film but is not how you test a refresh.

If you do want that, and OpenEMR times out rather than refusing, your IP has
rotated — mine changed twice in a day:

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
