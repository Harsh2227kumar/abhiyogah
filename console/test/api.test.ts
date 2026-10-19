import { readFileSync } from "node:fs";
import openapiTS, { astToString } from "openapi-typescript";
import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/client";
import { createHttpApi } from "@/lib/api/http";
import { createMockApi, pickSnapshot, type MockFixtures } from "@/lib/api/mock";
import fixtures from "@/mock/fixtures.json";

const data = fixtures as unknown as MockFixtures;
const api = createMockApi(data);

describe("generated client", () => {
  it("matches the OpenAPI document it was generated from", async () => {
    const spec = JSON.parse(readFileSync("mock/provisional.openapi.json", "utf8"));
    const fresh = astToString(await openapiTS(spec));
    const committed = readFileSync("lib/api/generated/schema.ts", "utf8");
    const body = (s: string) => s.slice(s.indexOf("export "));
    expect(body(committed)).toBe(body(fresh));
  });
});

describe("mock API", () => {
  it("serves the latest snapshot at or before as_of", () => {
    expect(pickSnapshot(data, "2026-10-20T09:00:00+05:30")?.as_of).toBe("2026-10-19T18:00:00+05:30");
    expect(pickSnapshot(data, "2026-10-19T18:00:00+05:30")?.as_of).toBe("2026-10-19T18:00:00+05:30");
    expect(pickSnapshot(data, "2026-01-01T00:00:00+05:30")).toBeUndefined();
  });

  it("defaults as_of to now", () => {
    const now = () => Date.parse("2026-10-22T00:00:00+05:30");
    expect(pickSnapshot(data, undefined, now)?.as_of).toBe("2026-10-21T18:00:00+05:30");
  });

  it("rejects a malformed as_of", () => {
    expect(() => pickSnapshot(data, "19-10-2026")).toThrow(ApiError);
  });

  it("shows the 20-day IO clock breach after time travel", async () => {
    const before = await api.getDecision("CMP-2026-000101", "IO-CB-2026-14-1-b", "2026-10-19T20:00:00+05:30");
    const after = await api.getDecision("CMP-2026-000101", "IO-CB-2026-14-1-b", "2026-10-21T20:00:00+05:30");
    expect(before.record.result).toBe("RUNNING");
    expect(after.record.result).toBe("BREACHED");
    expect(after.record.breach?.due_date).toBe("2026-10-19");
    expect(after.position).toBeGreaterThan(before.position);
  });

  it("reports the tampered ledger as broken", async () => {
    const c = await api.getComplaint("CMP-2026-000105", "2026-10-19T20:00:00+05:30");
    expect(c.chain.verified).toBe(false);
    expect(c.chain.broken_at).toBe(0);
  });

  it("404s an unknown complaint", async () => {
    await expect(api.getComplaint("CMP-NOPE")).rejects.toMatchObject({ status: 404 });
  });

  it("keeps every obligation in DRAFT or FUTURE_DATED without sign-off", async () => {
    for (const o of await api.listObligations()) {
      expect(["DRAFT", "FUTURE_DATED"]).toContain(o.status);
      expect(o.signed_off_by ?? null).toBeNull();
    }
  });
});

describe("http API", () => {
  it("builds query strings and raises ApiError on failure", async () => {
    const calls: string[] = [];
    const fake = (async (url: URL) => {
      calls.push(url.toString());
      return new Response("{}", { status: url.pathname.endsWith("/x") ? 404 : 200 });
    }) as unknown as typeof fetch;
    const http = createHttpApi("http://engine.test/api", fake);
    await http.listComplaints("2026-10-19T18:00:00+05:30");
    expect(calls[0]).toBe("http://engine.test/api/complaints?as_of=2026-10-19T18%3A00%3A00%2B05%3A30");
    await expect(http.getComplaint("x")).rejects.toBeInstanceOf(ApiError);
  });
});
