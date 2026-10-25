import { configureClient } from "./client";

/**
 * Settings read when an app starts, not baked in at build time.
 *
 * One build of an app can then be pointed at any backend by editing a small
 * `config.json` beside it — local development, a staging service, a deployed one
 * — without rebuilding. Every field is optional; with no file the app behaves as it
 * always has, talking to `/api` on its own origin.
 */
export interface RuntimeConfig {
  /** Where the API is. A path ("/api") behind a proxy, or a full URL. */
  apiBase?: string;
  /** Where the other apps are, for the one screen that shows several side by side. */
  apps?: Record<string, string>;
}

let current: RuntimeConfig = {};

export const runtimeConfig = (): RuntimeConfig => current;

/**
 * Fetch `config.json` and apply it. Never throws: a missing or malformed file
 * means "use the defaults", and a dev server that answers every unknown path with
 * the app's own HTML must not break startup.
 */
export async function loadRuntimeConfig(url = "/config.json"): Promise<RuntimeConfig> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    const type = response.headers.get("content-type") ?? "";
    if (response.ok && type.includes("json")) {
      current = (await response.json()) as RuntimeConfig;
      if (current.apiBase) configureClient({ baseUrl: current.apiBase });
    }
  } catch {
    current = {};
  }
  return current;
}

/** For tests. */
export function resetRuntimeConfig(): void {
  current = {};
}
