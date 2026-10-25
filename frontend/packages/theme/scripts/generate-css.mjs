import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { renderCss } from "./css.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const tokens = JSON.parse(readFileSync(resolve(here, "../src/tokens.json"), "utf8"));
writeFileSync(resolve(here, "../src/tokens.css"), renderCss(tokens));
console.log("wrote src/tokens.css");
