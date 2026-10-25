/**
 * Regenerate the Kotlin that mirrors the shared TypeScript packages.
 *
 *   node android/tools/generate.mjs
 *
 * Needs Node 22+ (it imports the TypeScript i18n source directly).
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { LANGS, STEP_WORDS, STRINGS } from "../../frontend/packages/i18n/src/i18n.ts";
import { renderTokens, renderTranslations } from "./kotlin.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../app/src/main/java/org/ekyatra/saathi");

const tokens = JSON.parse(
  readFileSync(resolve(here, "../../frontend/packages/theme/src/tokens.json"), "utf8"),
);

const outputs = {
  [resolve(src, "i18n/Translations.kt")]: renderTranslations({
    strings: STRINGS,
    stepWords: STEP_WORDS,
    langs: LANGS,
  }),
  [resolve(src, "ui/theme/Tokens.kt")]: renderTokens(tokens),
};

for (const [path, content] of Object.entries(outputs)) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
  console.log("wrote", path.replace(resolve(here, "../..") + "/", ""));
}
