export function renderCss(tokens: {
  color: Record<string, string>;
  radius: Record<string, number>;
  shadow: Record<string, string>;
  motion: { ease: string };
  layout: Record<string, number>;
}): string;
