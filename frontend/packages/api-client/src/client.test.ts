import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiUrl, configureClient, request, resetClient } from "./client";

const ok = (body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

describe("client", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    resetClient();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("defaults to /api so a dev-server proxy keeps working", () => {
    expect(apiUrl("/patients")).toBe("/api/patients");
  });

  it("uses a configured base URL and ignores a trailing slash", () => {
    configureClient({ baseUrl: "http://10.0.2.2:8000/api///" });
    expect(apiUrl("/live")).toBe("http://10.0.2.2:8000/api/live");
  });

  it("sends no authorization header until a token exists", async () => {
    fetchMock.mockReturnValue(ok([]));
    await request("/patients");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.authorization).toBeUndefined();
    expect(init.headers["content-type"]).toBe("application/json");
  });

  it("asks for the token on every request, so a refreshed one is used", async () => {
    let token = "first";
    configureClient({ getToken: () => token });
    fetchMock.mockImplementation(() => ok({}));

    await request("/a");
    token = "second";
    await request("/b");

    expect(fetchMock.mock.calls[0][1].headers.authorization).toBe("Bearer first");
    expect(fetchMock.mock.calls[1][1].headers.authorization).toBe("Bearer second");
  });

  it("lets a caller override a header", async () => {
    fetchMock.mockReturnValue(ok({}));
    await request("/x", { headers: { "content-type": "text/plain" } });
    expect(fetchMock.mock.calls[0][1].headers["content-type"]).toBe("text/plain");
  });

  it("turns a failure into an ApiError that carries the status", async () => {
    fetchMock.mockReturnValue(Promise.resolve(new Response("no", { status: 403 })));
    const error = await request("/disruptions/x/approve", { method: "POST" }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(403);
    expect(error.message).toBe("POST /disruptions/x/approve failed: 403");
  });
});
