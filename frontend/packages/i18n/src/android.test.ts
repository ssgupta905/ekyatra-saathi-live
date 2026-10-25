import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { renderTranslations } from "../../../../android/tools/kotlin.mjs";
import { LANGS, STEP_WORDS, STRINGS } from "./i18n";

const here = dirname(fileURLToPath(import.meta.url));
const kotlin = resolve(
  here,
  "../../../../android/app/src/main/java/org/ekyatra/saathi/i18n/Translations.kt",
);

describe("the Android app's words", () => {
  it("are the committed Kotlin generated from i18n.ts", () => {
    const expected = renderTranslations({ strings: STRINGS, stepWords: STEP_WORDS, langs: LANGS });
    expect(readFileSync(kotlin, "utf8"), "run `make android-strings`").toBe(expected);
  });
});
