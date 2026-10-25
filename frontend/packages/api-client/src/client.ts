/**
 * The one place a request leaves the app.
 *
 * Every app — the staff web apps, the family mobile app, the demo stage — talks
 * to the same API through this, so the three things that differ between them
 * are settings, not code:
 *
 *   where the API is   `baseUrl`   "/api" behind a dev proxy, a full URL on a
 *                                  phone or in a deployment
 *   who is asking      `getToken`  empty until login lands; then a bearer token
 *   how much to trust  nothing     errors carry the status and nothing else
 */

export interface ClientConfig {
  /** No trailing slash. Relative ("/api") works behind a dev-server proxy. */
  baseUrl: string;
  /** Called per request, so a refreshed token is picked up without a restart. */
  getToken?: () => string | null | undefined | Promise<string | null | undefined>;
  /**
   * A one-use ticket for the event stream, or null when nobody is signed in.
   * A browser's `EventSource` cannot send an Authorization header, and a token
   * in a URL ends up in logs; a ticket in the URL is worth nothing a minute later.
   */
  streamTicket?: () => Promise<string | null>;
  /** The server said the token is not (or no longer) good. Sign the person out. */
  onUnauthorized?: () => void;
}

const DEFAULT_BASE_URL = "/api";

let config: ClientConfig = { baseUrl: DEFAULT_BASE_URL };

const trimSlash = (url: string) => url.replace(/\/+$/, "");

export function configureClient(next: Partial<ClientConfig>): void {
  config = {
    ...config,
    ...next,
    baseUrl: trimSlash(next.baseUrl ?? config.baseUrl),
  };
}

/** Back to defaults. For tests. */
export function resetClient(): void {
  config = { baseUrl: DEFAULT_BASE_URL };
}

export const apiUrl = (path: string): string => `${config.baseUrl}${path}`;

/** Where the event stream is, with a ticket on it when sign-in is on. */
export async function streamUrl(): Promise<string> {
  const ticket = await config.streamTicket?.();
  return apiUrl(ticket ? `/stream?ticket=${encodeURIComponent(ticket)}` : "/stream");
}

export class ApiError extends Error {
  readonly status: number;
  /** What the server said was wrong, when it said (the body's `detail`). */
  readonly detail: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function authHeaders(): Promise<Record<string, string>> {
  const token = await config.getToken?.();
  return token ? { authorization: `Bearer ${token}` } : {};
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(await authHeaders()),
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  if (response.status === 401 && !path.startsWith("/auth/")) config.onUnauthorized?.();
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new ApiError(
      `${init?.method ?? "GET"} ${path} failed: ${response.status}`,
      response.status,
      body?.detail,
    );
  }
  return (await response.json()) as T;
}
