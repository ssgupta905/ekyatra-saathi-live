import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, request, resetClient } from "./client";
import { records } from "./records";

describe("records client", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    resetClient();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("keeps what the server said was wrong, so a screen can show it", async () => {
    const detail = { errors: [{ where: "row 3", message: "language is required" }] };
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 }));

    const error = (await request("/import/csv", { method: "POST" }).catch((e) => e)) as ApiError;

    expect(error.status).toBe(422);
    expect(error.detail).toEqual(detail);
  });

  it("still throws a plain ApiError when the failure has no JSON body", async () => {
    fetchMock.mockResolvedValue(new Response("gateway timeout", { status: 504 }));

    const error = (await request("/live").catch((e) => e)) as ApiError;

    expect(error.status).toBe(504);
    expect(error.detail).toBeUndefined();
  });

  it("sends a CSV as text/csv, not JSON, and says whether to commit", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response("{}", { status: 200 })));

    await records.importCsv("record_type,id\npatient,P1\n", false);
    await records.importCsv("x", true);

    const [first, second] = fetchMock.mock.calls;
    expect(first[0]).toBe("/api/import/csv?commit=false");
    expect(first[1].headers["content-type"]).toBe("text/csv");
    expect(first[1].body).toBe("record_type,id\npatient,P1\n");
    expect(second[0]).toBe("/api/import/csv?commit=true");
  });

  it("names the hospital on a FHIR import and passes the fallback distance only when given", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response("{}", { status: 200 })));

    await records.importFhir({ resourceType: "Bundle" }, { hospitalId: "TMH-MUM", commit: false });
    await records.importFhir(
      { resourceType: "Bundle" },
      { hospitalId: "TMH-MUM", commit: true, defaultDistanceKm: 1900 },
    );

    const [without, withDistance] = fetchMock.mock.calls.map((c) => c[0] as string);
    expect(without).toContain("hospital_id=TMH-MUM");
    expect(without).toContain("commit=false");
    expect(without).not.toContain("default_distance_km");
    expect(withDistance).toContain("default_distance_km=1900");
  });

  it("releases a report as the named person", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response("{}", { status: 200 })));

    await records.release("S-1", "Imran Shaikh");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/steps/S-1/release");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ by: "Imran Shaikh", note: "" });
  });
});
