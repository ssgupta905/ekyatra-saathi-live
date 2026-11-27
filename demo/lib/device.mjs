/**
 * Which handset, said out loud, every time.
 *
 * `adb shell …` with two devices attached fails with "more than one
 * device/emulator" and returns nothing. The film's `adb()` helper swallowed
 * that failure, so the moment a second device appeared every phone command
 * became a silent no-op: taps went nowhere, screens never changed, and the
 * take died several beats later complaining about something else entirely.
 * That is what happened the first time a real handset was plugged in beside
 * the emulator.
 *
 * So nothing here talks to "the phone". Everything takes a serial, chosen
 * once, and `-s` is not optional.
 *
 * `SAATHI_PHONE` picks it. With nothing set, a real handset wins over an
 * emulator — if somebody has gone to the trouble of plugging a phone in, that
 * is the one they mean to film.
 */

import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";

const run = promisify(execFile);

export const ADB =
  process.env.ADB ?? `${process.env.HOME}/Library/Android/sdk/platform-tools/adb`;

/** Every attached device, with enough to tell a handset from an emulator. */
export async function attached() {
  const { stdout } = await run(ADB, ["devices", "-l"]).catch(() => ({ stdout: "" }));
  return stdout
    .split("\n")
    .slice(1)
    .map((line) => line.trim())
    .filter((line) => line && line.includes("device "))
    .map((line) => {
      const serial = line.split(/\s+/)[0];
      const model = (line.match(/model:(\S+)/) ?? [])[1] ?? "";
      return { serial, model, emulator: serial.startsWith("emulator-") };
    });
}

/**
 * The handset to film.
 *
 * Throws rather than guesses when `SAATHI_PHONE` names something that is not
 * there — a take recorded against the wrong device looks exactly like a take
 * recorded against the right one until somebody watches it.
 */
export async function pickPhone(preferred = process.env.SAATHI_PHONE) {
  const devices = await attached();
  if (!devices.length) throw new Error("no device is attached; plug in a phone or start an emulator");

  if (preferred) {
    const found = devices.find((d) => d.serial === preferred);
    if (!found) {
      throw new Error(
        `SAATHI_PHONE=${preferred} is not attached. Attached: ` +
          devices.map((d) => `${d.serial} (${d.model})`).join(", "),
      );
    }
    return found;
  }

  // A real handset beats an emulator: somebody plugged it in on purpose.
  return devices.find((d) => !d.emulator) ?? devices[0];
}

/** The second device, for the beat that shows one disruption hitting two families. */
export async function pickSecond(firstSerial) {
  const devices = await attached();
  return devices.find((d) => d.serial !== firstSerial) ?? null;
}

/** `adb -s …`, with failures visible rather than swallowed. */
export function adbFor(serial) {
  const call = async (...args) => {
    try {
      return await run(ADB, ["-s", serial, ...args]);
    } catch (error) {
      // Loud on purpose. The silent version of this cost a take.
      throw new Error(`adb -s ${serial} ${args.join(" ")}: ${error.stderr || error.message}`);
    }
  };
  // `.quiet` for the handful of calls where failure genuinely does not matter
  // — pressing BACK on a screen that has no back, say.
  call.quiet = async (...args) =>
    run(ADB, ["-s", serial, ...args]).catch(() => ({ stdout: "" }));
  return call;
}

/**
 * Record a device's own screen to a file, with no window on the desktop.
 *
 * This is the whole reason the clips are safe. `scrcpy --no-window
 * --no-playback -r` pulls the device's video stream straight to disk, so
 * nothing about the recording depends on what is on the laptop — no editor,
 * no lock screen, no notification shade, no Continuity camera stealing the
 * capture index. A take can no longer accidentally film the desktop because
 * the desktop is never in the path.
 *
 * Returns a handle; call `stop()` and await it to finish the file cleanly.
 */
export function recordPhone(serial, file) {
  const child = spawn(
    "scrcpy",
    ["-s", serial, "--no-window", "--no-playback", "--record", file, "--record-format=mp4"],
    { stdio: ["ignore", "ignore", "pipe"] },
  );
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });

  return {
    file,
    stop: () =>
      new Promise((done, fail) => {
        child.on("close", (code) => {
          // scrcpy exits non-zero when interrupted, which is how we stop it.
          // A file that never appeared is the real failure.
          if (code !== 0 && /error|failed/i.test(stderr)) {
            fail(new Error(`scrcpy on ${serial}: ${stderr.trim().split("\n").slice(-2).join(" ")}`));
          } else {
            done(file);
          }
        });
        // SIGINT, not SIGKILL: scrcpy needs to write the moov atom or the mp4
        // is unplayable.
        child.kill("SIGINT");
      }),
  };
}
