import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiUrl, resetClient } from "./client";
import { loadRuntimeConfig, resetRuntimeConfig, runtimeConfig } from "./runtime";

const reply = (body: string, type = "application/json", status = 200) =>
  Promise.resolve(new Response(body, { status, headers: { "content-type": type } }));

describe("runtime config", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    resetClient();
    resetRuntimeConfig();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("points the client at the configured API", async () => {
    fetchMock.mockReturnValue(reply('{"apiBase":"https://api.example/api","apps":{"desk":"http://d"}}'));
    await loadRuntimeConfig();
    expect(apiUrl("/live")).toBe("https://api.example/api/live");
    expect(runtimeConfig().apps?.desk).toBe("http://d");
  });

  it("keeps the defaults when there is no file", async () => {
    fetchMock.mockReturnValue(reply("not found", "text/plain", 404));
    await loadRuntimeConfig();
    expect(apiUrl("/live")).toBe("/api/live");
  });

  it("ignores a dev server that answers every path with the app's own HTML", async () => {
    fetchMock.mockReturnValue(reply("<!doctype html><html></html>", "text/html"));
    expect(await loadRuntimeConfig()).toEqual({});
    expect(apiUrl("/live")).toBe("/api/live");
  });

  it("survives a network failure", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    expect(await loadRuntimeConfig()).toEqual({});
  });

  it("leaves the API alone when the file does not name one", async () => {
    fetchMock.mockReturnValue(reply('{"apps":{"family":"http://f"}}'));
    await loadRuntimeConfig();
    expect(apiUrl("/live")).toBe("/api/live");
  });
});
