# The end-to-end film

One film from the twelve separate recordings, cut to explain the whole system
in order: a family is taken on, the hospital's desk, three families on one
morning, the vendor's own screen, and then the same morning from the phone in
the family's hand.

    node film/cards.mjs            # the stills
    python film/narrate.py         # the voice-over (needs SARVAM_KEY)
    SAATHI_CLIPS_DIR=~/Downloads/demo-recordings node film/build.mjs

Output: `~/Documents/EKYATRA-Saathi-end-to-end.mp4`.

## Why it is built this way

**`plan.mjs` is the only place the edit lives.** The stills, the narration and
the assembly all read it. The moment the cut list exists in two files they
drift, and a film whose narration is a beat out of step with its picture is
worse than a film with no narration at all.

**The voice is Sarvam** — the same service the family's phone uses to read a
message aloud. Narrating a film about that system with a different voice would
have been an odd thing to do.

**Nothing is re-shot.** Every frame is from the recordings in
`~/Downloads/demo-recordings`, against the deployed service. The film only
chooses what to keep.

**The Hindi you hear is the phone's own read-aloud, re-spoken.** The source
recordings have no audio track at all — `adb screenrecord` captures none — so
the read-aloud you can *see* happening on screen was never recorded. Three
segments carry a `hindi` block in the plan: the exact sentence on screen at
that moment, transcribed from the frames, spoken by the same model the phone
called (`bulbul:v3`, hi-IN). Where one is present the English narration waits
for it instead of ducking under it, because the point of that chapter is to
hear the voice, and a narrator talking over a voice you cannot hear is the
wrong way round.

## What was cut, and why

The source recordings are honest but slow: they were made to prove things
worked, so they hold on a screen long after it has stopped changing. Roughly
half of the footage is that hold time.

| Source | Was | Kept | What went |
|---|---|---|---|
| `09-live-demo-control-centre` | 7:20 | 3:08 | Hold time at the end of each of the nine captioned steps, and three minutes of a network board that had stopped changing |
| `01-sign-in-email-otp` | 1:07 | 0:45 | The emulator's own Gboard contacts prompt, and a second attempt after the first code lapsed. Neither is the product |
| `02-anita-before-the-report` | 0:34 | 0:16 | Eighteen seconds of the Android home screen and the app's splash |
| `10-live-demo-anita-phone-hindi` | 2:46 | 0:30 | Ninety seconds of a static Wait screen either side of the one moment that matters — the flip to Come |
| `11-control-centre-walkthrough` | 1:34 | 1:27 | The Onboarding section, which showed "Nobody to take on yet". That was true for ten minutes in October and is wrong now; chapter 1 shows the real screen |
| `13`, `14`, `15` (phones) | 2:18, 2:04, 2:13 | 0:45, 0:54, 0:46 | Each one ends with a minute or more parked on the Today tab |
| `16-onboarding-medical-background` | 0:58 | 0:46 | A loading screen, and the clip's own burned-in title |
| `12-partner-app` | 0:31 | 0:21 | The same: an "Opening…" screen and a burned-in title |
| `17-what-the-family-can-manage` | 1:04 | 1:04 | Nothing — recorded for this film, so there is no hold time in it |

The last two are worth a word. Both clips open with a title card of their own,
burned in when they were recorded, and both say exactly what the film's chapter
card says three seconds earlier. Two title cards back to back reads as an edit
mistake rather than a flourish, so the clips' own titles go and the chapter
cards keep the job.

The cuts in `09` land on the caption changes — the frame numbers were read off
the footage, not guessed — so each one reads as a deliberate edit rather than
a jump.

## The one chapter that is not the deployed service

Chapter 9 runs against a **local** build. The budget conversation is new and the deployed
service answers `/budget` with a 404, so recording it there was not an option and
recording it anywhere else without saying so would have been the single dishonest thing
in the film. The closing card and the narration both say which chapters are which.

## What was left alone

`00-first-cut.mp4` is untouched. It is the 7 November assembly of clips 01-11
and still the record of what was shown that day.
