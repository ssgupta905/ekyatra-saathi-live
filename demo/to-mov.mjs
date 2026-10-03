/**
 * Turn a recording into a QuickTime .mov.
 *
 *     node to-mov.mjs ../recordings/<file>.webm [destination]
 *
 * Playwright can only write WebM/VP8. Nothing on a stock Mac decodes that:
 * AVFoundation refuses the file outright, so `avconvert`, QuickTime and
 * Preview all fail, and renaming it to .mp4 does not convert anything — it
 * just hides the problem until something tries to play it.
 *
 * There are two decoders present on this machine and neither is ffmpeg. Chrome
 * decodes VP8 and can *encode* H.264 through MediaRecorder, and AVFoundation
 * reads H.264 happily. So the conversion is two real steps:
 *
 *   webm/VP8  --(Chrome: decode, re-encode)-->  mp4/H.264  --(avconvert)-->  mov
 *
 * The first step runs at playback speed, because MediaRecorder records a live
 * stream — a four-minute film takes four minutes. The re-encode is lossy on
 * top of a lossy source, so the bitrate is set high enough that the text on
 * screen stays sharp, which is the whole point of this particular film.
 */

import { chromium } from "playwright";
import { execFile } from "node:child_process";
import { appendFileSync, mkdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { basename, dirname, extname, resolve } from "node:path";
import { homedir } from "node:os";
import { promisify } from "node:util";

const run = promisify(execFile);

const source = resolve(process.argv[2] ?? "");
const stem = basename(source, extname(source));
const destination = resolve(process.argv[3] ?? resolve(homedir(), "Documents"), `${stem}.mov`);

if (!statSync(source, { throwIfNoEntry: false })) {
  console.error(`no such recording: ${source}`);
  process.exit(1);
}

mkdirSync(dirname(destination), { recursive: true });
const interim = resolve(dirname(destination), `.${stem}.h264.mp4`);
rmSync(interim, { force: true });

console.log(`reading   ${source}`);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

// Chunks come back as base64 and are appended straight to disk, so a long
// recording never has to exist twice in memory.
await page.exposeFunction("__chunk", (b64) => {
  appendFileSync(interim, Buffer.from(b64, "base64"));
});
await page.exposeFunction("__log", (message) => console.log(`  ${message}`));

const b64 = readFileSync(source).toString("base64");
await page.setContent(
  `<body style="margin:0;background:#000">
     <video id="v" muted playsinline
            src="data:video/webm;base64,${b64}"></video></body>`,
);

const result = await page.evaluate(async () => {
  const video = document.getElementById("v");
  await new Promise((done) => {
    if (video.readyState >= 2) return done();
    video.onloadeddata = done;
  });

  const { duration, videoWidth: width, videoHeight: height } = video;
  window.__log(`${width}x${height}, ${duration.toFixed(1)}s`);

  const stream = video.captureStream();
  const recorder = new MediaRecorder(stream, {
    mimeType: "video/mp4;codecs=avc1.640028",
    // Generous: this film is almost entirely small text on light panels, and
    // a thrifty bitrate turns 13px labels into mush.
    videoBitsPerSecond: 16_000_000,
  });

  const toBase64 = (buffer) => {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    }
    return btoa(binary);
  };

  const pending = [];
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      pending.push(event.data.arrayBuffer().then((b) => window.__chunk(toBase64(b))));
    }
  };

  const finished = new Promise((done) => {
    recorder.onstop = done;
  });

  recorder.start(1000);
  await video.play();
  await new Promise((done) => {
    video.onended = done;
  });
  // A beat, so the encoder flushes the tail rather than clipping the last card.
  await new Promise((done) => setTimeout(done, 600));
  recorder.stop();
  await finished;
  await Promise.all(pending);

  return { duration, width, height };
});

await browser.close();

const encoded = statSync(interim);
console.log(`encoded   ${(encoded.size / 1e6).toFixed(1)} MB of H.264`);

// AVFoundation reads H.264 without complaint, so this step is a rewrap into a
// QuickTime container rather than another generation of re-encoding.
console.log(`wrapping  ${destination}`);
try {
  await run("/usr/bin/avconvert", [
    "--preset", "PresetPassthrough",
    "--source", interim,
    "--output", destination,
    "--replace",
  ]);
} catch (error) {
  console.error("avconvert refused the re-encoded file:");
  console.error(String(error.stderr || error).slice(0, 400));
  console.error(`\nThe H.264 version is still here and plays: ${interim}`);
  process.exit(1);
}
rmSync(interim, { force: true });

const out = statSync(destination);
console.log(
  `\n${destination}\n${(out.size / 1e6).toFixed(1)} MB · ${result.width}x${result.height} · ` +
    `${result.duration.toFixed(0)}s`,
);
