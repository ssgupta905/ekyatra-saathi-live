export function renderTranslations(input: {
  strings: Record<string, object>;
  stepWords: Record<string, Record<string, string>>;
  langs: { code: string; label: string; endonym: string }[];
}): string;

export function renderTokens(tokens: {
  color: Record<string, string>;
  radius: Record<string, number>;
}): string;

export function argb(value: string): string;
