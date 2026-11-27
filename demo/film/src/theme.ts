/**
 * One palette, shared by every scene.
 *
 * Taken from the product's own tokens rather than invented for the film, so a
 * viewer moving between an illustrated scene and a screen recording does not
 * feel the join. The ink is near-black rather than black and the ground is
 * near-white rather than white, which is what stops a 1080p render looking
 * like a slide deck.
 */
export const C = {
  ground: "#0B1020",
  groundSoft: "#131A2E",
  paper: "#F7F8FB",
  ink: "#0D1220",
  inkSoft: "#5A6477",
  line: "#D8DEE9",
  blue: "#2563EB",
  blueSoft: "#DBE5FB",
  warn: "#B45309",
  warnSoft: "#FEF0DC",
  go: "#047857",
  goSoft: "#D7F0E6",
  stop: "#B91C1C",
};

export const FONT =
  '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif';

export const FPS = 30;
