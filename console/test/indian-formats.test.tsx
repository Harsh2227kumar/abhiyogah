import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DecisionPage from "@/app/complaints/[id]/decisions/[obligationId]/page";
import ComplaintPage from "@/app/complaints/[id]/page";
import BoardPage from "@/app/page";
import RulesPage from "@/app/rules/page";

const AS_OF = "2026-10-21T18:00:00+05:30";
const search = Promise.resolve({ as_of: AS_OF });

/** Visible text outside <code> (identifiers, hashes and rule syntax are shown verbatim). */
function prose(container: HTMLElement): string {
  const clone = container.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("code").forEach((c) => c.remove());
  const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) parts.push(n.textContent ?? "");
  return parts.join(" ");
}

const pages = {
  board: () => BoardPage({ searchParams: search }),
  complaint: () => ComplaintPage({ params: Promise.resolve({ id: "CMP-2026-000101" }), searchParams: search }),
  decision: () =>
    DecisionPage({
      params: Promise.resolve({ id: "CMP-2026-000101", obligationId: "IO-CB-2026-14-1-b" }),
      searchParams: search,
    }),
  rules: () => RulesPage({ searchParams: Promise.resolve({}) }),
};

describe("Indian formats on every page", () => {
  for (const [name, load] of Object.entries(pages)) {
    it(`${name}: no ISO dates or raw paise in prose`, async () => {
      const { container } = render(await load());
      const text = prose(container);
      expect(text).not.toMatch(/\b\d{4}-\d{2}-\d{2}\b/);
      expect(text).not.toMatch(/amount_paise: \d/);
      expect(text).toMatch(/\b\d{2}-\d{2}-\d{4}\b/);
    });
  }

  it("shows the LLM-extracted amount in rupees in the event payload", async () => {
    const { container } = render(await pages.complaint());
    expect(prose(container)).toContain("amount_paise: ₹2,450.00");
  });

  it("shows ₹ compensation parameters in the rule browser", async () => {
    const { container } = render(await pages.rules());
    expect(prose(container)).toContain("₹100.00");
  });
});
