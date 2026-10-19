import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DecisionPage from "@/app/complaints/[id]/decisions/[obligationId]/page";
import type { DecisionReplay } from "@/lib/api";
import { AS_OF, recorded, replayFetch } from "./recorded";

const page = async (id: string, obligationId: string, as_of: string) =>
  render(await DecisionPage({ params: Promise.resolve({ id, obligationId }), searchParams: Promise.resolve({ as_of }) }));

describe("decision replay on the recorded API", () => {
  it("renders the clause-cited trace of the IO 20-day obligation", async () => {
    await page("CMP-DEMO-0101", "IO-CB-2026-14-1-b", AS_OF.now);
    const source = screen.getByRole("region", { name: "Obligation" });
    expect(source.textContent).toContain("cl. 14(1)(b)");
    expect(within(source).getByText("Draft")).toBeDefined();
    expect(within(source).getByRole("link", { name: "source text" }).getAttribute("href")).toMatch(/^https:\/\//);
    const maxDays = within(screen.getByRole("region", { name: "Parameters" })).getByText("max_days").closest("tr")!;
    expect(maxDays.textContent).toContain("20");
    expect(maxDays.textContent).toContain("14-01-2026");
    expect(within(screen.getByRole("region", { name: "Inputs" })).getByText("Wholly rejected")).toBeDefined();
    expect(screen.getByRole("region", { name: "Trace" }).querySelectorAll("li").length).toBeGreaterThan(0);
    const ledger = screen.getByRole("region", { name: "Ledger" });
    expect(ledger.textContent).toMatch(/[0-9a-f]{64}/);
    expect(ledger.textContent).toContain("Verified");
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("after time travel, flags that the live result differs from the stored record", async () => {
    await page("CMP-DEMO-0101", "IO-CB-2026-14-1-b", AS_OF.later);
    const note = screen.getByRole("note");
    expect(note.textContent).toContain("Breached");
    expect(note.textContent).toContain("latest one in the ledger");
  });

  it("warns when the chain is broken before this record", async () => {
    const path = "/complaints/CMP-DEMO-0101/decisions/IO-CB-2026-14-1-b";
    const replay = recorded<DecisionReplay>(path, AS_OF.now);
    replay.chain = { ...replay.chain, verified: false, broken_at: 0, reason: "HASH_MISMATCH" };
    vi.stubGlobal("fetch", (async (input: URL) =>
      new URL(input).pathname === path
        ? new Response(JSON.stringify(replay), { status: 200 })
        : replayFetch(input)) as typeof fetch);
    await page("CMP-DEMO-0101", "IO-CB-2026-14-1-b", AS_OF.now);
    expect(screen.getByRole("region", { name: "Ledger" }).textContent).toContain("cannot be trusted");
  });
});
