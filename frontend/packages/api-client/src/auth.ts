/**
 * Signing in, and remembering that you did.
 *
 * The token lives in `localStorage`, which each app has to itself (every app is
 * its own origin), so signing in as a doctor on one tab does not make another
 * app think you are one. Where storage is blocked it lives in memory and the
 * person signs in again on reload, which is the safe way to fail.
 */

import { configureClient, request } from "./client";

export interface Principal {
  id: string;
  name: string;
  role: "navigator" | "doctor" | "desk" | "admin" | "caregiver" | "patient";
  /** For a caregiver: the families they may see. Empty for staff. */
  patient_ids: string[];
}

export interface Session {
  token: string;
  expires_in: number;
  principal: Principal;
}

export type Contact = { phone: string; email?: never } | { email: string; phone?: never };

export interface AuthConfig {
  required: boolean;
  provider: string;
}

const KEY = "saathi.token";
let memory: string | null = null;

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(KEY) ?? memory;
    } catch {
      return memory;
    }
  },
  set(token: string): void {
    memory = token;
    try {
      localStorage.setItem(KEY, token);
    } catch {
      /* in memory only */
    }
  },
  clear(): void {
    memory = null;
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* nothing to clear */
    }
  },
};

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const auth = {
  config: () => request<AuthConfig>("/auth/config"),
  login: (username: string, password: string) =>
    post<Session>("/auth/login", { username, password }),
  /** A family is reached by a phone number or an email address, never both. */
  requestOtp: (contact: Contact) => post<{ sent: boolean }>("/auth/otp/request", contact),
  verifyOtp: (contact: Contact, code: string) =>
    post<Session>("/auth/otp/verify", { ...contact, code }),
  me: () => request<Principal>("/auth/me"),
  streamTicket: () => request<{ ticket: string }>("/auth/stream-ticket", { method: "POST" }),
};

/**
 * Point the shared client at the stored token. Call once per app, before it
 * renders; `onUnauthorized` is how an expired token ends up at the sign-in page.
 */
export function installAuth(onUnauthorized: () => void): void {
  configureClient({
    getToken: () => tokenStore.get(),
    streamTicket: async () => (tokenStore.get() ? (await auth.streamTicket()).ticket : null),
    onUnauthorized: () => {
      tokenStore.clear();
      onUnauthorized();
    },
  });
}
