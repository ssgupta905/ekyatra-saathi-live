import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { auth, installAuth, tokenStore } from "./auth";
import { request, resetClient, streamUrl } from "./client";

describe("signing in", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    resetClient();
    tokenStore.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  const reply = (body: unknown, status = 200) =>
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify(body), { status })));

  it("remembers a token even where storage is blocked", () => {
    tokenStore.set("abc");
    expect(tokenStore.get()).toBe("abc");
    tokenStore.clear();
    expect(tokenStore.get()).toBeNull();
  });

  it("sends the token on every request once installed", async () => {
    installAuth(() => undefined);
    tokenStore.set("abc");
    reply({});

    await request("/patients");

    expect(fetchMock.mock.calls[0][1].headers.authorization).toBe("Bearer abc");
  });

  it("signs the person out when the server stops trusting the token", async () => {
    const out = vi.fn();
    installAuth(out);
    tokenStore.set("stale");
    reply({ detail: "sign in first" }, 401);

    await request("/patients").catch(() => undefined);

    expect(out).toHaveBeenCalledTimes(1);
    expect(tokenStore.get()).toBeNull();
  });

  it("does not treat a wrong password as an expired session", async () => {
    const out = vi.fn();
    installAuth(out);
    reply({ detail: "wrong username or password" }, 401);

    await auth.login("seema", "nope").catch(() => undefined);

    expect(out).not.toHaveBeenCalled();
  });

  it("opens the stream with a ticket when signed in, and without one when not", async () => {
    installAuth(() => undefined);
    expect(await streamUrl()).toBe("/api/stream");

    tokenStore.set("abc");
    reply({ ticket: "t 1" });
    expect(await streamUrl()).toBe("/api/stream?ticket=t%201");
  });
});
