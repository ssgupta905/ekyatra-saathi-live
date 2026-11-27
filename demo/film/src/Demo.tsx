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
  /**
   * Which reel this line belongs to. Absent for the film proper.
   *
   * "next" is a roadmap section: intention, not working software. "built" is
   * the addendum recorded after two of those roadmap features were built —
   * working software again, and badged so nobody has to remember which.
   */
  part?: "next" | "built";
  /**
   * Seconds of navigation to cut off the front of the clip.
   *
   * A recorded Console clip opens with somebody clicking through the rail to
   * reach the thing the section is about. That is dead screen under a voice
   * already describing what comes after it — the narration leads the picture,
   * and the viewer is told about a refusal while watching a sidebar. The
   * lead-in is deterministic (the recorder's own waits), so it is measured
   * and cut rather than guessed at by eye.
   */
  trim?: number;
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
  "next-divider": S.NextDivider,
  "next-molecular": S.MolecularNext,
  "next-partners": S.PartnerNext,
  "built-divider": S.BuiltDivider,
  "built-limits": S.BuiltLimits,
  "built-close": S.BuiltClose,
  readiness: S.Readiness,
  guard: S.Guard,
  roles: S.Roles,
  limits: S.Limits,
  ledger: S.Ledger,
  closing: S.Closing,
};

/** Which clips actually exist, written by `demo/stage-clips.mjs`. */
import { CLIPS as HAVE } from "./clips";

/** A breath after each line, so sentences do not run into one another. */
const TAIL = 0.65;

/**
 * How much faster than life a recording may be played.
 *
 * Timing used to come from the narration alone, which meant a section ended
 * when the sentence did — and a sixty-second clip got sixteen seconds. The
 * film showed a quarter of the journey recording and none of the route, the
 * maps hand-off or the family's own spends, so half the product was in the
 * clips and absent from the film.
 *
 * A section is now long enough to play its whole clip, at natural speed.
 * This was 1.8x for a while to hold the film near nine minutes, and brisk is
 * not the same as followable: a navigator moving through a queue at nearly
 * twice life is hard to read and impossible to trust. The film is longer
 * instead, which is the right trade for a demo whose whole claim is that you
 * can watch it work.
 */
const MAX_SPEED = 1.0;

/**
 * Clips whose own sound is part of the point.
 *
 * Saathi reading a plan aloud in Hindi is the thing this project is most
 * often asked to prove, and it was being thrown away — the clip muted, the
 * narration asserting a voice the viewer was never played. These clips keep
 * their audio, and are never sped up: a 1.8x voice is a chipmunk, which
 * would be worse than silence.
 */
const AUDIBLE = new Set(["14-read-aloud"]);

const isAudible = (line: Line) => Boolean(line.clip && AUDIBLE.has(line.clip));

const usable = (script.lines as Line[]).filter((line) => !line.clip || HAVE[line.clip]);

/**
 * The film proper, and the roadmap that follows it.
 *
 * Kept as two compositions rather than one, for a reason that is practical
 * rather than aesthetic: the main film is nineteen minutes of mostly video and
 * takes the better part of an hour to render, because every frame goes through
 * a browser. The roadmap is seventy seconds of drawn scenes and renders in
 * about a minute. Splitting them means appending a slide does not cost an hour,
 * and the finished film is concatenated rather than re-encoded.
 */
export const lines: Line[] = usable.filter((line) => !line.part);
export const nextLines: Line[] = usable.filter((line) => line.part === "next");
//: The addendum: the two roadmap features, now recorded running.
export const builtLines: Line[] = usable.filter((line) => line.part === "built");

/** Seconds of clip this line has to show, after any dead lead-in is cut. */
const clipSeconds = (line: Line) =>
  line.clip ? Math.max(0, (HAVE[line.clip]?.seconds ?? 0) - (line.trim ?? 0)) : 0;

/**
 * A roadmap scene is read, not watched.
 *
 * The clips elsewhere move, and the narration carries them. These two are
 * dense slides — three columns of bullets, a row of chips — and the voice
 * finishes well before anybody has got through the third column. They hold
 * for a while after the narrator stops, which is the difference between a
 * slide somebody read and a slide that went past.
 */
const READING_TAIL = 10;

export const secondsFor = (line: Line) =>
  Math.max(
    (line.seconds ?? 4) +
      // A drawn roadmap scene is read, not watched, so it is held open past
      // the sentence that introduces it. A divider has nothing to read.
      (line.scene && line.part && !line.scene.endsWith("-divider") ? READING_TAIL : TAIL),
    clipSeconds(line) / (isAudible(line) ? 1 : MAX_SPEED),
  );

export const framesFor = (line: Line) => Math.round(secondsFor(line) * FPS);

/** Never slower than life; only as fast as it must be to fit. */
export const speedFor = (line: Line) =>
  isAudible(line) ? 1 : Math.max(1, clipSeconds(line) / secondsFor(line));

export const totalFrames = () =>
  Math.max(FPS, lines.reduce((sum, line) => sum + framesFor(line), 0));

export const nextFrames = () =>
  Math.max(FPS, nextLines.reduce((sum, line) => sum + framesFor(line), 0));

export const builtFrames = () =>
  Math.max(FPS, builtLines.reduce((sum, line) => sum + framesFor(line), 0));

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
const Clip: React.FC<{
  file: string;
  label: string;
  speed: number;
  audible: boolean;
  narrationFrames: number;
  trimFrames: number;
}> = ({ file, label, speed, audible, narrationFrames, trimFrames }) => (
  <AbsoluteFill style={{ backgroundColor: C.ground }}>
    <OffthreadVideo
      src={staticFile(`clips/${file}`)}
      style={{ width: "100%", height: "100%", objectFit: "contain" }}
      playbackRate={speed}
      trimBefore={trimFrames || undefined}
      muted={!audible}
      // Under the narrator while he is speaking, then up. The app's voice is
      // the evidence; the narration is the frame around it, and they must not
      // talk over each other.
      volume={audible
        ? (f) =>
            interpolate(f, [0, narrationFrames - 12, narrationFrames + 12], [0.18, 0.18, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
        : 0}
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

/**
 * Which surface a clip is of, so a viewer is never guessing.
 *
 * The fall-through is the hazard here: a clip nobody added a rule for is
 * labelled as the family's phone, and a Console recording captioned "the
 * family · phone" tells the viewer something false about who is looking at
 * what. It happened — the addendum's eight clips were all labelled that way
 * on the first cut. New clips go above the fall-through, not after it.
 */
const whichSurface = (clip: string) => {
  if (/hospital-leave|written-back|appointments/.test(clip)) return "The hospital · OpenEMR";
  if (/vendor-applies/.test(clip)) return "A vendor · partner app";
  if (/directory-switched-off|review-queue|letting-them-in/.test(clip)) {
    return "The administrator · Console";
  }
  if (/no-consent|hold-a-finding|already-done/.test(clip)) return "The doctor · Console";
  if (/its-own-consent/.test(clip)) return "The navigator · Console";
  if (/board|person-agrees|planner|approves|pretend|worth/.test(clip)) return "The navigator · Console";
  if (/partner/.test(clip)) return "A partner";
  if (/without-a-smartphone/.test(clip)) return "The family · browser";
  if (/second-family/.test(clip)) return "A second household";
  return "The family · phone";
};

/* ──────────────────────────────── the film ─────────────────────────────── */

const Reel: React.FC<{ of: Line[] }> = ({ of: reel }) => {
  let at = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: C.ground }}>
      {reel.map((line) => {
        const length = framesFor(line);
        const from = at;
        at += length;
        const Scene = line.scene ? SCENES[line.scene] : null;
        return (
          <Sequence key={line.id} from={from} durationInFrames={length}>
            <Dissolve length={length}>
              {line.clip ? (
                <Clip
                  file={HAVE[line.clip].file}
                  label={whichSurface(line.clip)}
                  speed={speedFor(line)}
                  audible={isAudible(line)}
                  narrationFrames={Math.round(((line.seconds ?? 4) + TAIL) * FPS)}
                  trimFrames={Math.round((line.trim ?? 0) * FPS)}
                />
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

export const Demo: React.FC = () => <Reel of={lines} />;
export const Roadmap: React.FC = () => <Reel of={nextLines} />;
export const Built: React.FC = () => <Reel of={builtLines} />;
