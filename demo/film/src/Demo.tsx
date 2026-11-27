import React from "react";
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { C, FONT, FPS } from "./theme";
import * as S from "./Scenes";
import script from "./script.json";

/**
 * The film: illustrated scenes and recorded clips, in one order, under one voice.
 *
 * Timing comes from the narration rather than from anybody's guess. Every line
 * is spoken first, its duration measured and written back into `script.json`
 * by `demo/narrate.py`, and each section lasts exactly as long as its line
 * plus a breath. A caption timed by hand drifts the moment a sentence is
 * reworded; this cannot.
 *
 * Two rules the composition enforces:
 *
 * **A clip is evidence, an illustration is explanation.** Where a line has a
 * `clip`, the screen shows the recording of that thing happening. Where it has
 * a `scene`, the screen is drawn. A claim about what this system does is never
 * made over an illustration.
 *
 * **A missing clip is a missing section, not a silent one.** If a clip could
 * not be shot, the section is dropped entirely — picture and narration
 * together — rather than leaving a voice describing a black screen.
 */

type Line = {
  id: string;
  text: string;
  clip?: string;
  scene?: string;
  seconds?: number;
};

const SCENES: Record<string, React.FC> = {
  logo: S.Logo,
  "problem-distance": S.Distance,
  "problem-money": S.Money,
  "problem-wasted": S.Wasted,
  "problem-sequence": S.Sequence,
  "solution-network": S.Network,
  "solution-agents": S.Agents,
  "solution-money": S.MoneyRules,
  closing: S.Closing,
};

/** Which clips actually exist, written by `demo/stage-clips.mjs`. */
import { CLIPS as HAVE } from "./clips";

/** A breath after each line, so sentences do not run into one another. */
const TAIL = 0.65;

export const lines: Line[] = (script.lines as Line[]).filter(
  (line) => !line.clip || HAVE[line.clip],
);

export const framesFor = (line: Line) => Math.round(((line.seconds ?? 4) + TAIL) * FPS);

export const totalFrames = () =>
  Math.max(FPS, lines.reduce((sum, line) => sum + framesFor(line), 0));

/* ────────────────────────────── the furniture ──────────────────────────── */

/** A dissolve at both ends, so cuts between surfaces do not jar. */
const Dissolve: React.FC<{ children: React.ReactNode; length: number }> = ({ children, length }) => {
  const frame = useCurrentFrame();
  const fade = 9;
  const opacity = interpolate(
    frame,
    [0, fade, Math.max(fade + 1, length - fade), length],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

/**
 * A recorded surface, letterboxed rather than cropped.
 *
 * A phone is 1080x2340 and a console is 1600x1000; forcing either to 16:9
 * would cut something off, and what gets cut is always the thing the clip is
 * about. `contain` keeps all of it and puts the ground either side.
 */
const Clip: React.FC<{ file: string; label: string }> = ({ file, label }) => (
  <AbsoluteFill style={{ backgroundColor: C.ground }}>
    <OffthreadVideo
      src={staticFile(`clips/${file}`)}
      style={{ width: "100%", height: "100%", objectFit: "contain" }}
      muted
    />
    <div
      style={{
        position: "absolute",
        left: 54,
        top: 44,
        padding: "11px 20px",
        borderRadius: 999,
        background: "rgba(11,16,32,.72)",
        color: "rgba(247,248,251,.9)",
        fontFamily: FONT,
        fontSize: 21,
        letterSpacing: 1.5,
        textTransform: "uppercase",
      }}
    >
      {label}
    </div>
  </AbsoluteFill>
);

/** The spoken line, also on screen — rooms are noisy and some viewers read. */
const Caption: React.FC<{ text: string }> = ({ text }) => (
  <AbsoluteFill style={{ justifyContent: "flex-end", pointerEvents: "none" }}>
    <div
      style={{
        margin: "0 64px 54px",
        padding: "22px 30px",
        borderRadius: 16,
        background: "rgba(11,16,32,.84)",
        color: C.paper,
        fontFamily: FONT,
        fontSize: 29,
        lineHeight: 1.42,
      }}
    >
      {text}
    </div>
  </AbsoluteFill>
);

/** Which surface a clip is of, so a viewer is never guessing. */
const whichSurface = (clip: string) => {
  if (/hospital-leave|written-back|appointments/.test(clip)) return "The hospital · OpenEMR";
  if (/board|person-agrees|planner|approves|pretend|worth/.test(clip)) return "The navigator · Console";
  if (/partner/.test(clip)) return "A partner";
  if (/without-a-smartphone/.test(clip)) return "The family · browser";
  if (/second-family/.test(clip)) return "A second household";
  return "The family · phone";
};

/* ──────────────────────────────── the film ─────────────────────────────── */

export const Demo: React.FC = () => {
  let at = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: C.ground }}>
      {lines.map((line) => {
        const length = framesFor(line);
        const from = at;
        at += length;
        const Scene = line.scene ? SCENES[line.scene] : null;
        return (
          <Sequence key={line.id} from={from} durationInFrames={length}>
            <Dissolve length={length}>
              {line.clip ? (
                <Clip file={HAVE[line.clip]} label={whichSurface(line.clip)} />
              ) : Scene ? (
                <Scene />
              ) : (
                <AbsoluteFill style={{ backgroundColor: C.ground }} />
              )}
              {/* Illustrated scenes carry their own words; a clip needs the line. */}
              {line.clip && <Caption text={line.text} />}
            </Dissolve>
            <Audio src={staticFile(`vo/${line.id}.wav`)} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
