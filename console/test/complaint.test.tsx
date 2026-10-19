import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ComplaintPage from "@/app/complaints/[id]/page";
import { displayFact, provenanceLabel } from "@/lib/complaint";
import { AS_OF } from "./recorded";

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

describe("complaint page on the recorded API", () => {
  it("before day 20: IO referral is required, the reversal breach owes compensation", async () => {
    await page("CMP-DEMO-0101", AS_OF.now);
    const breaches = screen.getByRole("region", { name: "Breaches" });
    expect(within(breaches).queryByText("IO-CB-2026-14-1-b")).toBeNull();
    expect(breaches.textContent).toMatch(/TAT-2019-FAILED-TXN.*compensation ₹[\d,]+\.00/);
    const actions = screen.getByRole("region", { name: "Required actions" });
    expect(within(actions).getByText("Refer to IO")).toBeDefined();
    const facts = screen.getByRole("region", { name: "Facts" });
    const amount = within(facts).getByText("₹2,450.00").closest("tr")!;
    expect(within(amount).getByText("LLM").dataset.source).toBe("LLM");
    expect(within(screen.getByRole("region", { name: "Event timeline" })).getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getByText(/Decision ledger verified/)).toBeDefined();
  });

  it("after time travel: the 20-day IO clock is breached", async () => {
    await page("CMP-DEMO-0101", AS_OF.later);
    const breaches = screen.getByRole("region", { name: "Breaches" });
    expect(within(breaches).getByText("IO-CB-2026-14-1-b").closest("li")!.textContent).toContain("not stopped — 1 day late");
  });
});
