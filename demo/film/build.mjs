/**
 * Assembles the film: one intermediate per segment, then a concat.
 *
 *     SAATHI_CLIPS_DIR=~/Downloads/demo-recordings node film/build.mjs
 *
 * One pass per segment rather than a single enormous filter graph, because a
 * graph that long fails as a unit and tells you almost nothing about which
 * segment broke it. Intermediates are written with identical codec settings so
 * the final join is a stream copy.
 *
 * Three shapes of segment:
 *   card     a still, held
 *   browser  a 16:9-ish screen recording, fitted and letterboxed
 *   phone    a tall screen recording, stood on the left beside its panel
 *
 * Audio is always present, even where nobody speaks: a film whose track drops
 * out between chapters sounds broken rather than quiet.
 */

import { execFile } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { CANVAS, INK, PLAN } from "./plan.mjs";

const run = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const BUILD = resolve(HERE, "build");
const ART = resolve(BUILD, "art");
const VO = resolve(BUILD, "vo");
const PARTS = resolve(BUILD, "parts");

const CLIPS =
  process.env.SAATHI_CLIPS_DIR ??
  resolve(process.env.HOME ?? HERE, "Downloads/demo-recordings");
const OUT =
  process.env.SAATHI_FILM_OUT ??
  resolve(process.env.HOME ?? HERE, "Documents/EKYATRA-Saathi-end-to-end.mp4");

const { w, h, fps } = CANVAS;

/** Fit inside the canvas without cropping, and letterbox the rest in ink. */
const fitted = `scale=${w}:${h}:force_original_aspect_ratio=decrease,pad=${w}:${h}:(ow-iw)/2:(oh-ih)/2:${INK}`;

/** The phone stands 1000px tall on the left; its panel occupies the right. */
const PHONE_H = 1000;
const PHONE_X = 200;
const PANEL_X = 760;

function videoFilter(seg) {
  if (seg.kind === "card") return `scale=${w}:${h},fps=${fps},format=yuv420p`;
  if (seg.kind === "browser") return `${fitted},fps=${fps},format=yuv420p`;
  return null; // phone needs a two-input graph
}

/**
 * Seek *before* the input, never after it.
 *
 * An `-ss` written after `-i` is not a late seek on that file — it is an input
 * option belonging to the *next* `-i`, which here is the voice-over. A first
 * attempt at this had `-i clip.mp4 -ss 2 -t 17 -i voice.wav`, which left the
 * picture untrimmed and seeked the narration instead. Before `-i` it is both
 * fast and frame-accurate: ffmpeg lands on the preceding keyframe and decodes
 * forward to the exact time, which matters because these cuts have to sit on
 * a caption change.
 *
 * Length is an output option, applied once at the end, for the same reason.
 */
function seek(seg) {
  return seg.in > 0
    ? ["-ss", String(seg.in), "-i", resolve(CLIPS, seg.file)]
    : ["-i", resolve(CLIPS, seg.file)];
}

function args(seg) {
  const secs = seg.seconds.toFixed(3);
  const out = resolve(PARTS, `${seg.id}.mp4`);
  const voice = resolve(VO, `${seg.id}.wav`);
  const hasVoice = existsSync(voice);

  const input = [];
  let filter;

  if (seg.kind === "card") {
    input.push("-loop", "1", "-i", resolve(ART, `${seg.id}.png`));
    filter = `[0:v]${videoFilter(seg)}[v]`;
  } else if (seg.kind === "browser") {
    input.push(...seek(seg));
    filter = `[0:v]${videoFilter(seg)}[v]`;
  } else {
    input.push(...seek(seg));
    input.push("-i", resolve(ART, `${seg.id}.png`));
    filter =
      `color=c=${INK}:s=${w}x${h}:r=${fps}:d=${secs}[bg];` +
      `[0:v]scale=-1:${PHONE_H},fps=${fps}[ph];` +
      `[bg][ph]overlay=${PHONE_X}:(H-h)/2:shortest=1[a];` +
      `[a][1:v]overlay=${PANEL_X}:0:format=auto,format=yuv420p[v]`;
  }

  // Silence is laid down first so every part has the same audio shape; the
  // voice is mixed on top and the pad guarantees the exact segment length.
  const silence = `anullsrc=channel_layout=stereo:sample_rate=48000`;
  if (hasVoice) {
    input.push("-i", voice);
    const voiceIn = seg.kind === "phone" ? "2:a" : "1:a";
    filter +=
      `;${silence}:d=${secs}[sil];` +
      `[${voiceIn}]aresample=48000,aformat=channel_layouts=stereo,` +
      `afade=t=in:st=0:d=0.12[vo];` +
      `[sil][vo]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,` +
      `apad,atrim=0:${secs},asetpts=N/SR/TB[a]`;
  } else {
    filter += `;${silence}:d=${secs}[a]`;
  }

  return [
    "-v", "error", "-y",
    ...input,
    "-filter_complex", filter,
    "-map", "[v]", "-map", "[a]",
    "-t", secs,
    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
    "-pix_fmt", "yuv420p", "-r", String(fps),
    "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
    "-movflags", "+faststart",
    out,
  ];
}

async function seconds(file) {
  const { stdout } = await run("ffprobe", [
    "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", file,
  ]);
  return Number(stdout.trim());
}

mkdirSync(PARTS, { recursive: true });

for (const seg of PLAN) {
  process.stdout.write(`  ${seg.id.padEnd(15)}`);
  const started = Date.now();
  await run("ffmpeg", args(seg), { maxBuffer: 1 << 24 });
  //: Measured, not planned. The length printed here used to be the number out
  //: of the plan, which is exactly the number that cannot reveal a trim that
  //: silently did not happen.
  const got = await seconds(resolve(PARTS, `${seg.id}.mp4`));
  const drift = Math.abs(got - seg.seconds);
  if (drift > 0.15) throw new Error(`${seg.id}: wanted ${seg.seconds}s, got ${got.toFixed(2)}s`);
  console.log(`${got.toFixed(1)}s  (${((Date.now() - started) / 1000).toFixed(1)}s)`);
}

const list = resolve(BUILD, "parts.txt");
writeFileSync(list, PLAN.map((s) => `file '${resolve(PARTS, `${s.id}.mp4`)}'`).join("\n"));

console.log("\n  joining…");
await run("ffmpeg", [
  "-v", "error", "-y",
  "-f", "concat", "-safe", "0", "-i", list,
  "-c", "copy", "-movflags", "+faststart",
  OUT,
], { maxBuffer: 1 << 24 });

const { stdout } = await run("ffprobe", [
  "-v", "error", "-show_entries", "format=duration,size",
  "-of", "default=nk=1:nw=1", OUT,
]);
const [duration, size] = stdout.trim().split("\n").map(Number);
console.log(
  `\n  ${OUT}\n  ${Math.floor(duration / 60)}:${String(Math.round(duration % 60)).padStart(2, "0")}` +
    `  ${(size / 1e6).toFixed(1)} MB`,
);
