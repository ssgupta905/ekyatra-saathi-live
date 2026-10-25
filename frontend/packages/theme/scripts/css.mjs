/**
 * tokens.json -> CSS custom properties.
 *
 * The variable names are the ones the stylesheet already uses (`--plane`,
 * `--r-md`, `--shadow-card`...), so generating them changes nothing visible.
 */

const px = (n) => `${n}px`;

export function renderCss(tokens) {
  const lines = [];
  const add = (name, value) => lines.push(`  --${name}: ${value};`);

  for (const [name, value] of Object.entries(tokens.color)) add(name, value);
  for (const [name, value] of Object.entries(tokens.radius)) add(`r-${name}`, px(value));
  for (const [name, value] of Object.entries(tokens.shadow)) {
    add(name === "ring" ? "ring" : `shadow-${name}`, value);
  }
  add("ease", tokens.motion.ease);
  for (const [name, value] of Object.entries(tokens.layout)) add(name, px(value));
  add("chrome-h", "calc(var(--header-h) + var(--story-bar-h))");

  return [
    "/* Generated from tokens.json by scripts/generate-css.mjs. Do not edit. */",
    ":root {",
    ...lines,
    "}",
    "",
  ].join("\n");
}
