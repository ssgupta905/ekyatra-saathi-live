import narration from "../narration.json";
import durations from "./durations.json";
import clips from "./clips.json";

export const FPS = 30;
/** Breath after each line, so scenes never talk over each other. */
const TAIL_S = 0.9;
/** A chapter title card between chapters: silent, a beat to breathe. */
const CHAPTER_S = 2.6;
/** Frames two neighbouring scenes overlap while one hands over to the next. */
export const TRANSITION = 18;

export type Clip = { file: string; kind: "screen" | "phone"; from: number; to: number };
export type Scene = {
  id: string;
  chapter: string;
  visual: string;
  text: string;
  clip?: Clip;
  audio: string | null;
  frames: number;
  /** The screen clip shown behind a phone, pushed back and blurred. */
  behind?: Clip;
};

const clipMap = clips as Record<string, Clip>;
const dur = durations as Record<string, number>;

export const SCENES: Scene[] = (() => {
  const out: Scene[] = [];
  let lastScreen: Clip | undefined;
  let lastChapter = "";
  let chapterNo = 0;
  for (const s of narration.scenes as Array<{ id: string; chapter: string; visual: string; text: string; clip?: string }>) {
    const seconds = (dur[s.id] ?? 5) + TAIL_S + (s.visual === "logo" ? 1.5 : 0);
    const clip = s.clip ? clipMap[s.clip] : undefined;
    if (s.clip && !clip) continue; // not recorded yet
    if (s.visual !== "logo" && s.chapter !== lastChapter && s.chapter !== "Saathi") {
      chapterNo += 1;
      out.push({
        id: `CH${chapterNo}`, chapter: s.chapter, visual: "chapter", text: String(chapterNo),
        audio: null, frames: Math.round(CHAPTER_S * FPS) + TRANSITION,
      });
    }
    lastChapter = s.chapter;
    out.push({
      id: s.id,
      chapter: s.chapter,
      visual: clip ? (clip.kind === "phone" ? "phone" : "screen") : s.visual,
      text: s.text,
      clip,
      audio: `audio/${s.id}.wav`,
      frames: Math.round(seconds * FPS) + TRANSITION,
      behind: clip?.kind === "phone" ? lastScreen : undefined,
    });
    if (clip?.kind === "screen") lastScreen = clip;
  }
  return out;
})();

export const TOTAL_FRAMES =
  SCENES.reduce((n, s) => n + s.frames, 0) - TRANSITION * Math.max(0, SCENES.length - 1);
