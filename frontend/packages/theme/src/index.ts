/**
 * Design tokens as plain values, for anything that is not CSS (React Native).
 * Web apps import `@saathi/theme/tokens.css` instead; both come from the same
 * `tokens.json`, and a test fails if the generated CSS goes stale.
 */

import tokens from "./tokens.json";

export const colors = tokens.color;
export const radii = tokens.radius;
export const fonts = tokens.font;
export const shadows = tokens.shadow;
export const nativeShadows = tokens.native;
export const layout = tokens.layout;

export type ColorName = keyof typeof tokens.color;

export { tokens };
