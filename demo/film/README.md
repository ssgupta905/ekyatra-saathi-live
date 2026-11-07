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

The last two are worth a word. Both clips open with a title card of their own,
burned in when they were recorded, and both say exactly what the film's chapter
card says three seconds earlier. Two title cards back to back reads as an edit
mistake rather than a flourish, so the clips' own titles go and the chapter
cards keep the job.

The cuts in `09` land on the caption changes — the frame numbers were read off
the footage, not guessed — so each one reads as a deliberate edit rather than
a jump.

## What was left alone

`00-first-cut.mp4` is untouched. It is the 7 November assembly of clips 01-11
and still the record of what was shown that day.
