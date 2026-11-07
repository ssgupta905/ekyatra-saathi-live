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

/**
 * Making the Hindi sound like it is coming out of the phone on screen.
 *
 * A different voice was the first half of this (see `narrate.py`); this is the
 * second. A small device speaker has almost no bass and no air, and squashes
 * its dynamics, so the band is cut to roughly what one reproduces and the
 * result is compressed and set slightly back in the mix.
 *
 * Without it the Hindi arrives at full studio bandwidth, sitting in exactly
 * the same acoustic space as the narration — and a voice in the narrator's
 * space is heard as the narrator, whatever language it is speaking.
 */
const PHONE_SPEAKER =
  //: Telephone band. A first attempt at 400-3600 Hz measured almost the same
  //: as the narration, because this text-to-speech has little energy up there
  //: to remove — so the band is narrowed to what a small speaker actually
  //: reproduces and the mids are pushed, which is what gives a phone its
  //: boxy sound. Verified by comparing band energy against the narration
  //: rather than by ear.
  "highpass=f=500,lowpass=f=3200," +
  "equalizer=f=2000:width_type=q:width=1.0:g=5," +
  "acompressor=threshold=-20dB:ratio=6:attack=3:release=80," +
  "volume=0.95";

/**
 * How long the Hindi runs, and therefore when the narrator may start.
 *
 * The English waits rather than ducking under it. Ducking would have been less
 * code, but chapter seven exists to let you *hear* the voice the family hears,
 * and a narrator explaining a voice playing underneath them is the wrong way
 * round.
 */
function voiceStart(seg, hindiSeconds) {
  return seg.hindi ? seg.hindi.at + hindiSeconds + 0.6 : 0;
}

function args(seg, hindiSeconds = 0) {
  const secs = seg.seconds.toFixed(3);
  const out = resolve(PARTS, `${seg.id}.mp4`);
  const voice = resolve(VO, `${seg.id}.wav`);
  const hindi = resolve(VO, `${seg.id}.hi.wav`);
  const hasVoice = existsSync(voice);
  const hasHindi = seg.hindi != null && existsSync(hindi);

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
  // voices are mixed on top and the pad guarantees the exact segment length.
  const silence = `anullsrc=channel_layout=stereo:sample_rate=48000`;
  //: Inputs so far: the picture (and, for a phone segment, its panel). Audio
  //: inputs are appended after those, so their stream indices are counted
  //: rather than hard-coded — getting that wrong once already meant a segment
  //: seeking its narration instead of its video.
  let next = seg.kind === "phone" ? 2 : 1;
  const mixed = ["[sil]"];
  filter += `;${silence}:d=${secs}[sil]`;

  if (hasHindi) {
    input.push("-i", hindi);
    const at = Math.round(seg.hindi.at * 1000);
    filter +=
      `;[${next}:a]aresample=48000,aformat=channel_layouts=stereo,` +
      `${PHONE_SPEAKER},adelay=${at}|${at}[hi]`;
    mixed.push("[hi]");
    next += 1;
  }
  if (hasVoice) {
    input.push("-i", voice);
    const start = Math.round(voiceStart(seg, hindiSeconds) * 1000);
    const delay = start > 0 ? `,adelay=${start}|${start}` : "";
    filter +=
      `;[${next}:a]aresample=48000,aformat=channel_layouts=stereo,` +
      `afade=t=in:st=0:d=0.12${delay}[vo]`;
    mixed.push("[vo]");
    next += 1;
  }

  filter +=
    mixed.length > 1
      ? `;${mixed.join("")}amix=inputs=${mixed.length}:duration=first:` +
        `dropout_transition=0:normalize=0,apad,atrim=0:${secs},asetpts=N/SR/TB[a]`
      : `;[sil]anull[a]`;

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

  let hindiSeconds = 0;
  if (seg.hindi) {
    const file = resolve(VO, `${seg.id}.hi.wav`);
    if (!existsSync(file)) throw new Error(`${seg.id}: no Hindi audio — run narrate.py`);
    hindiSeconds = await seconds(file);
    //: Checked here rather than discovered in the finished film. If the
    //: narration would run past the end of the segment it is cut off mid
    //: sentence, which is the kind of thing that survives a casual watch.
    const voFile = resolve(VO, `${seg.id}.wav`);
    if (existsSync(voFile)) {
      const ends = voiceStart(seg, hindiSeconds) + (await seconds(voFile));
      if (ends > seg.seconds) {
        throw new Error(
          `${seg.id}: Hindi then narration ends at ${ends.toFixed(1)}s, ` +
            `past the segment's ${seg.seconds}s`,
        );
      }
    }
  }

  await run("ffmpeg", args(seg, hindiSeconds), { maxBuffer: 1 << 24 });
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
