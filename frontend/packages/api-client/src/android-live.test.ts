import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { PATIENT_KINDS } from "./live";

/**
 * The phone and the browser must agree on which events matter.
 *
 * Both clients refresh a family's page only when an event kind they recognise
 * arrives. A kind missing from one of them fails in the quietest way there
 * is: no error, no warning, just a screen that never updates. Nine kinds were
 * added here and not to the Kotlin, and the result was a family being asked a
 * question whose phone did not know until it was closed and reopened.
 *
 * The Kotlin is read as text on purpose — there is no way to import it — so
 * this is a contract test in the same spirit as the i18n one next door.
 */
const here = dirname(fileURLToPath(import.meta.url));
const kotlin = resolve(
  here,
  "../../../../android/app/src/main/java/org/ekyatra/saathi/data/Live.kt",
);

function androidPatientKinds(source: string): Set<string> {
  const block = /val PatientKinds: Set<String> = setOf\(([\s\S]*?)\)/.exec(source);
  if (!block) throw new Error("PatientKinds not found in Live.kt — has it been renamed?");
  return new Set([...block[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]));
}

describe("the phone and the browser", () => {
  it("agree on which events change a family's page", () => {
    const android = androidPatientKinds(readFileSync(kotlin, "utf8"));
    const web = new Set<string>(PATIENT_KINDS);
    const missingOnThePhone = [...web].filter((k) => !android.has(k)).sort();
    const missingOnTheWeb = [...android].filter((k) => !web.has(k)).sort();
    expect(missingOnThePhone, "kinds the web refreshes on and the phone ignores").toEqual([]);
    expect(missingOnTheWeb, "kinds the phone refreshes on and the web ignores").toEqual([]);
  });
});
