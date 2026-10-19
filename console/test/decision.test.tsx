import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DecisionPage from "@/app/complaints/[id]/decisions/[obligationId]/page";

const page = async (id: string, obligationId: string, as_of: string) =>
  render(await DecisionPage({ params: Promise.resolve({ id, obligationId }), searchParams: Promise.resolve({ as_of }) }));

describe("decision replay", () => {
  it("renders the clause-cited trace of the IO 20-day breach", async () => {
    await page("CMP-2026-000101", "IO-CB-2026-14-1-b", "2026-10-21T18:00:00+05:30");
    const source = screen.getByRole("region", { name: "Obligation" });
    expect(source.textContent).toContain("cl. 14(1)(b)");
    expect(within(source).getByText("Draft")).toBeDefined();
    expect(within(source).getByRole("link", { name: "source text" }).getAttribute("href")).toMatch(/^https:\/\//);
    const params = screen.getByRole("region", { name: "Parameters" });
    const maxDays = within(params).getByText("max_days").closest("tr")!;
    expect(maxDays.textContent).toContain("20");
    expect(maxDays.textContent).toContain("14-01-2026");
    const inputs = screen.getByRole("region", { name: "Inputs" });
    expect(within(inputs).getByText("29-09-2026")).toBeDefined();
    expect(within(inputs).getByText("Wholly rejected")).toBeDefined();
    expect(screen.getByRole("region", { name: "Trace" }).querySelectorAll("li").length).toBeGreaterThan(0);
    const outcome = screen.getByRole("region", { name: "Deadline and outcome" });
    expect(outcome.textContent).toContain("19-10-2026");
    expect(outcome.textContent).toContain("2 days late");
    const ledger = screen.getByRole("region", { name: "Ledger" });
    expect(ledger.textContent).toMatch(/[0-9a-f]{64}/);
    expect(ledger.textContent).toContain("Verified");
  });

  it("warns when the chain is broken before this record", async () => {
    await page("CMP-2026-000105", "IO-CB-2026-14-9", "2026-10-19T18:00:00+05:30");
    expect(screen.getByRole("region", { name: "Ledger" }).textContent).toContain("cannot be trusted");
  });
});
