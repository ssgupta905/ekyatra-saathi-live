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

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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
  if (!response.ok) {
    throw new ApiError(
      `${init?.method ?? "GET"} ${path} failed: ${response.status}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}
