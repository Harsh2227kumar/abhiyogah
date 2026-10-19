import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ComplaintPage from "@/app/complaints/[id]/page";
import { displayFact, provenanceLabel } from "@/lib/complaint";

const page = async (id: string, as_of: string) =>
  render(await ComplaintPage({ params: Promise.resolve({ id }), searchParams: Promise.resolve({ as_of }) }));

describe("fact display", () => {
  it("formats dates, paise and codes", () => {
    expect(displayFact("bank_receipt_date", "2026-09-29")).toBe("29-09-2026");
    expect(displayFact("transaction_date_t", "2026-09-27")).toBe("27-09-2026");
    expect(displayFact("amount_paise", 245000)).toBe("₹2,450.00");
    expect(displayFact("channel", "UPI_P2P")).toBe("UPI P2P");
  });

  it("labels LLM provenance with model and prompt version", () => {
    expect(provenanceLabel({ source: "LLM", model: "m", prompt_version: "v1" })).toBe("LLM m · prompt v1");
    expect(provenanceLabel({ source: "HUMAN", actor: "a" })).toBe("Human · a");
  });
});

describe("complaint page", () => {
  it("shows the IO breach, the required action and LLM-sourced facts", async () => {
    await page("CMP-2026-000101", "2026-10-21T18:00:00+05:30");
    const breaches = screen.getByRole("region", { name: "Breaches" });
    expect(within(breaches).getByText("IO-CB-2026-14-1-b")).toBeDefined();
    expect(breaches.textContent).toContain("due 19-10-2026, not stopped — 2 days late");
    const actions = screen.getByRole("region", { name: "Required actions" });
    expect(within(actions).getByText("Refer to IO")).toBeDefined();
    const facts = screen.getByRole("region", { name: "Facts" });
    const amount = within(facts).getByText("₹2,450.00").closest("tr")!;
    expect(within(amount).getByText("LLM").dataset.source).toBe("LLM");
    const timeline = screen.getByRole("region", { name: "Event timeline" });
    expect(within(timeline).getAllByRole("listitem")).toHaveLength(4);
  });

  it("reports a broken decision chain", async () => {
    await page("CMP-2026-000105", "2026-10-19T18:00:00+05:30");
    expect(screen.getByText(/Decision chain broken at record 0/)).toBeDefined();
  });
});
