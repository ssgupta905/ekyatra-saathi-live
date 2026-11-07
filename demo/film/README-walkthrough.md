# The submission walkthrough

    SAATHI_FILM=walkthrough node film/cards.mjs
    SAATHI_FILM=walkthrough python film/narrate.py
    SAATHI_FILM=walkthrough node film/build.mjs

Output: `~/Documents/EKYATRA-Saathi-demo-walkthrough.mp4` (9:09).

## Why this exists separately from the end-to-end film

The brief asks for a narrated walkthrough that introduces the team, says how
the problem was approached, credits the technology and doctor partners, and
shows the working product — and says explicitly that it must not be "merely a
screen recording".

The 12-minute end-to-end film is a very good screen recording and nothing
else. It has no team, no approach, no partners. Rather than re-cut it, this
plan **quotes** it: a `film` segment lifts a passage out of
`EKYATRA-Saathi-end-to-end.mp4` with its own audio intact — composited
footage, its own narration, and the phone's Hindi read-aloud — and the new
material is built around it.

That is also why the product sections needed no new narration. They are
already narrated.

## What it does not have

**A person on camera.** This is assembled and narrated, not filmed. If the
team wants a face, the natural place is a short piece recorded to camera at
the front and the back; the rest stands as it is.

## Shape

The product is introduced before anybody is introduced, because the single
most misread thing about this is that it looks like a hospital system. It is
not one. Saying so takes twenty seconds and changes how the rest is watched.

| | |
|---|---|
| 0:00 | Title |
| 0:06 | **What this is** — not an HMS; an orchestration layer the HMS can call |
| 0:28 | Why that layer is missing, with the published figures |
| 0:51 | **Where it sits** — the architecture, before a single screen |
| 1:32 | What it is built from |
| 2:02 | Who built it — four names, twenty seconds |
| 2:22 | Dr Arani Chakraborty, and the limits of a process review |
| 2:49 | **The product, running** — seven passages quoted from the film |
| 8:14 | Does it address the problem |
| 8:47 | Close |

Roughly a third is narration over stills and two thirds is the product
working, which is the ratio the brief asks for.

## Two things worth knowing about the build

**Excerpts are trimmed inside the filter graph, not with `-ss` alone.** A plain
seek moved audio and video independently and the sound came back about a
second behind the picture, so two passages chosen to end in silence ended on a
half-spoken word instead. `trim` and `atrim` at matching timestamps keep them
locked.

**The narration is read at pace 1.1 in short sentences.** Synthesising the same
passage as one long sentence and as several short ones, then measuring the
spread of the fundamental frequency: long 21.5 Hz, short 26.7 Hz, short at
this pace 34.0 Hz. Slowing it down made it flatter, which is the opposite of
what you would guess. Voice samples for picking a different narrator are in
`~/Documents/voice-samples/`; `SAATHI_NARRATOR` swaps it.
