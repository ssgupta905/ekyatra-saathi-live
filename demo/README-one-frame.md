# Why the single-frame film is composited, not screen-captured

Two ways to get the hospital, the Console and the phone into one frame.

**Screen capture** (`one-frame.mjs`) tiles the three windows and records the
whole display with ffmpeg. It is the purest version — one continuous capture
of exactly what a person sees — and it needs **a screen-recording permission
granted once** to whatever launches ffmpeg. Until that is granted, macOS puts
a consent dialog in the middle of the frame and it appears in every take.

To use it: System Settings → Privacy & Security → Screen & System Audio
Recording → enable it for your terminal (or VS Code, if you run it there).
Then `make demo-one-frame`. Also close anything else on the display — the
tiling covers the screen, but a floating window will still show through.

**Simultaneous capture** (`make demo-connected`) is the default, and needs no
permission. The browser is recorded by Playwright and the phone by
`adb screenrecord` — both started at the same moment, during the same run —
and the two are laid side by side afterwards.

The difference matters and is worth being precise about on stage:

* both are **one run**. The leave entered in OpenEMR, the Console reacting
  and the phone speaking are the same events at the same wall-clock moment,
  not two takes spliced.
* in the composited version the two views are placed side by side in post,
  because they were recorded by two different recorders. Nothing is
  re-timed: they start together and run at the same rate.
* this is not the earlier film, which genuinely was two separate runs joined
  by a card. That one said so, and this one is a different thing.

If a judge asks whether the two halves are really simultaneous, the honest
answer is yes, and the proof is the clock in the phone's status bar against
the timestamps in the Console's event log.
