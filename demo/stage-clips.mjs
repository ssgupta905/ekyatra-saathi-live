/**
 * Put the recorded clips where Remotion can see them, and say which exist.
 *
 * Two jobs, both small and both load-bearing.
 *
 * **Convert.** Playwright writes `.webm` (VP8) and scrcpy writes `.mp4`
 * (H.264). Remotion will play both, but mixing codecs in one render is slow
 * and occasionally seeks badly, so everything becomes H.264 mp4 at a fixed
 * frame rate first.
 *
 * **Declare.** `public/clips/index.json` lists only the clips that actually
 * exist. The composition reads it and drops any section whose clip is
 * missing — picture *and* narration together — so a failed shoot can never
 * leave a voice describing a black screen. A film that quietly narrates
 * something nobody can see is worse than a shorter film.
 */

import { execFile } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const FROM = resolve(HERE, "../recordings/clips");
const TO = resolve(HERE, "film/public/clips");

async function main() {
  if (!existsSync(FROM)) throw new Error(`no clips at ${FROM}`);
  mkdirSync(TO, { recursive: true });

  const sources = readdirSync(FROM)
    .filter((f) => /\.(webm|mp4)$/.test(f))
    .sort();

  const index = {};
  for (const source of sources) {
    const name = source.replace(/\.(webm|mp4)$/, "");
    const out = `${name}.mp4`;
    process.stdout.write(`  ${name} … `);
    try {
      await run("ffmpeg", [
        "-y", "-i", resolve(FROM, source),
        // 30fps to match the composition; -an because every clip is silent
        // except the phone, and the phone's own audio would fight the
        // narration. The app's voice is demonstrated by the caption saying so.
        "-r", "30", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        resolve(TO, out),
      ]);
      const { stdout } = await run("ffprobe", [
        "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1", resolve(TO, out),
      ]);
      index[name] = out;
      console.log(`${Number(stdout).toFixed(1)}s`);
    } catch (error) {
      console.log(`failed — left out of the film (${String(error.message).split("\n")[0]})`);
    }
  }

  // A module in `src`, not JSON in `public`. `public/` is for files the
  // browser fetches at runtime; importing from it makes the bundler resolve
  // something it is not meant to own, and the root component then hangs on
  // load rather than failing with anything readable.
  writeFileSync(
    resolve(HERE, "film/src/clips.ts"),
    "// Written by demo/stage-clips.mjs. Which clips exist, so the composition\n" +
      "// can drop a section whose clip was never shot — picture and narration\n" +
      "// together, rather than leaving a voice over a black screen.\n" +
      `export const CLIPS: Record<string, string> = ${JSON.stringify(index, null, 2)};\n`,
  );
  console.log(`\n  ${Object.keys(index).length} clips staged in film/public/clips\n`);
}

main().catch((error) => {
  console.error(`\n  ${error.message}\n`);
  process.exit(1);
});
