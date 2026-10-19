import { readFileSync } from "node:fs";
import openapiTS, { astToString } from "openapi-typescript";
import { describe, expect, it } from "vitest";
import { ApiError, getApi } from "@/lib/api";
import { createHttpApi } from "@/lib/api/http";
import { AS_OF } from "./recorded";

describe("generated client", () => {
  it("matches the engine's openapi.json", async () => {
    const spec = JSON.parse(readFileSync("../openapi.json", "utf8"));
    const fresh = astToString(await openapiTS(spec));
    const committed = readFileSync("lib/api/generated/schema.ts", "utf8");
    const body = (s: string) => s.slice(s.indexOf("export "));
    expect(body(committed)).toBe(body(fresh));
  });
});

describe("getApi", () => {
  it("needs the API URL and key", () => {
    expect(() => getApi({})).toThrow(ApiError);
    expect(() => getApi({ ABHIYOGAH_API_URL: "http://x" })).toThrow(/ABHIYOGAH_API_KEY/);
  });
});

describe("http API against the recording", () => {
  it("shows the 20-day IO clock breach after time travel", async () => {
    const api = getApi();
    const now = await api.getComplaint("CMP-DEMO-0101", AS_OF.now);
    const later = await api.getComplaint("CMP-DEMO-0101", AS_OF.later);
    const io = (c: typeof now) => c.deadlines.find((d) => d.obligation_id === "IO-CB-2026-14-1-b");
    expect(io(now)?.result).toBe("RUNNING");
    expect(io(later)?.result).toBe("BREACHED");
    expect(later.breaches.map((b) => b.breach.obligation_id)).toContain("IO-CB-2026-14-1-b");
    expect(later.chain.verified).toBe(true);
  });

  it("raises ApiError with the server's detail on 404", async () => {
    await expect(getApi().getComplaint("CMP-NOPE", AS_OF.now)).rejects.toMatchObject({ status: 404 });
  });

  it("keeps every obligation DRAFT or FUTURE_DATED without sign-off", async () => {
    for (const o of await getApi().listObligations()) {
      expect(["DRAFT", "FUTURE_DATED"]).toContain(o.status);
      expect(o.signed_off_by ?? null).toBeNull();
    }
  });

  it("sends the API key and as_of", async () => {
    const calls: [string, Headers][] = [];
    const fake = (async (url: URL, init?: RequestInit) => {
      calls.push([url.toString(), new Headers(init?.headers)]);
      return new Response(JSON.stringify({ detail: "as_of needs role ADMIN" }), { status: 403 });
    }) as unknown as typeof fetch;
    const http = createHttpApi("http://engine.test/api", "k-123", fake);
    await expect(http.listComplaints("2026-10-19T18:00:00+05:30")).rejects.toThrow("403 from GET /api/complaints: as_of needs role ADMIN");
    expect(calls[0]![0]).toBe("http://engine.test/api/complaints?as_of=2026-10-19T18%3A00%3A00%2B05%3A30");
    expect(calls[0]![1].get("x-api-key")).toBe("k-123");
  });
});
