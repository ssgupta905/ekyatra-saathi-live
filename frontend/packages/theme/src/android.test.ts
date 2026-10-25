import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { argb, renderTokens } from "../../../../android/tools/kotlin.mjs";
import tokens from "./tokens.json";

const here = dirname(fileURLToPath(import.meta.url));
const kotlin = resolve(
  here,
  "../../../../android/app/src/main/java/org/ekyatra/saathi/ui/theme/Tokens.kt",
);

describe("the Android app's design tokens", () => {
  it("are the committed Kotlin generated from tokens.json", () => {
    expect(readFileSync(kotlin, "utf8"), "run `make android-strings`").toBe(renderTokens(tokens));
  });

  it("convert colours to Android's ARGB order", () => {
    expect(argb("#1c7a33")).toBe("0xFF1C7A33");
    // 0.72 of 255 is 184, which is B8.
    expect(argb("rgba(255, 255, 255, 0.72)")).toBe("0xB8FFFFFF");
    expect(argb("rgba(0, 0, 0, 0.06)")).toBe("0x0F000000");
    expect(argb("#fff")).toBe("0xFFFFFFFF");
  });
});
