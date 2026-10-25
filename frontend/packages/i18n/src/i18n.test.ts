import { describe, expect, it } from "vitest";
import { LANGS, STEP_WORDS, STRINGS, localDate, localDateShort, stepWord, t, type Lang } from "./i18n";

const codes = LANGS.map((l) => l.code);

describe("the four languages", () => {
  it("are all registered", () => {
    expect(codes.sort()).toEqual(["bn", "en", "hi", "or"]);
  });

  it("have exactly the same set of strings", () => {
    // A family reading Odia must never hit a missing label that Hindi has.
    const reference = Object.keys(STRINGS.en).sort();
    for (const lang of codes) {
      expect(Object.keys(STRINGS[lang]).sort(), lang).toEqual(reference);
    }
  });

  it("have no empty string", () => {
    for (const lang of codes) {
      for (const [key, value] of Object.entries(STRINGS[lang])) {
        if (typeof value === "string") expect(value.trim(), `${lang}.${key}`).not.toBe("");
      }
    }
  });

  it("name every pathway step in the three Indic languages", () => {
    const kinds = Object.keys(STEP_WORDS.hi);
    expect(kinds.length).toBeGreaterThanOrEqual(12);
    for (const lang of ["hi", "bn", "or"] as Lang[]) {
      expect(Object.keys(STEP_WORDS[lang]).sort(), lang).toEqual([...kinds].sort());
    }
  });
});

describe("t", () => {
  it("falls back to English for an unknown language", () => {
    expect(t("xx" as Lang)).toBe(STRINGS.en);
  });
});

describe("stepWord", () => {
  it("returns the translation, or the backend's own words when there is none", () => {
    expect(stepWord("biopsy", "Biopsy", "hi")).toBe(STEP_WORDS.hi.biopsy);
    expect(stepWord("biopsy", "Biopsy", "en")).toBe("Biopsy");
    expect(stepWord("not_a_step", "Fallback", "hi")).toBe("Fallback");
  });
});

describe("dates", () => {
  it("render a missing date as a dash", () => {
    expect(localDate(null, "hi")).toBe("—");
    expect(localDateShort(null, "or")).toBe("—");
  });

  it("render in the family's own script", () => {
    // Hermes (React Native) can ship without Indic locale data; this test is
    // the canary for that, here on Node and again on the device.
    expect(localDateShort("2026-10-27", "hi")).toMatch(/[ऀ-ॿ]/);
    expect(localDateShort("2026-10-27", "bn")).toMatch(/[ঀ-৿]/);
    expect(localDateShort("2026-10-27", "or")).toMatch(/[଀-୿]/);
  });
});
