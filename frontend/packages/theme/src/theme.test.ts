import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { renderCss } from "../scripts/css.mjs";
import { colors, radii } from "./index";
import tokens from "./tokens.json";

const here = dirname(fileURLToPath(import.meta.url));

describe("theme", () => {
  it("keeps the generated CSS in step with tokens.json", () => {
    const onDisk = readFileSync(resolve(here, "tokens.css"), "utf8");
    expect(onDisk, "run `npm run generate -w @saathi/theme`").toBe(renderCss(tokens));
  });

  it("emits every colour as a custom property", () => {
    const css = readFileSync(resolve(here, "tokens.css"), "utf8");
    for (const [name, value] of Object.entries(colors)) {
      expect(css).toContain(`--${name}: ${value};`);
    }
  });

  it("gives React Native numeric radii", () => {
    expect(radii.md).toBe(12);
    expect(typeof radii.pill).toBe("number");
  });

  it("keeps the four status hues, each with a tint", () => {
    for (const status of ["go", "wait", "uncertain", "critical"] as const) {
      expect(colors[status]).toMatch(/^#/);
      expect(colors[`${status}-tint` as keyof typeof colors]).toMatch(/^#/);
    }
  });
});
