import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RulesPage from "@/app/rules/page";
import { getApi, type Obligation } from "@/lib/api";
import { filterRules, formatParam, parameterRows, warnings } from "@/lib/rules";

const page = async (params: Record<string, string> = {}) =>
  render(await RulesPage({ searchParams: Promise.resolve(params) }));

const byId = async (id: string): Promise<Obligation> =>
  (await getApi().listObligations()).find((o) => o.obligation_id === id)!;

describe("rule helpers", () => {
  it("flags drafts, unverified rules and open questions", async () => {
    expect(warnings(await byId("TAT-2019-ILLEGIBLE-ROWS"))).toEqual([
      "Draft: not signed off by the owner",
      "Unverified: no primary text read",
      "Open question Q5",
    ]);
    expect(warnings(await byId("RBCCB-2026-AMEND3-FRAUD"))[0]).toMatch(/^Not yet in force/);
  });

  it("lists dated parameter values", async () => {
    const rows = parameterRows(await byId("IO-CB-2026-14-1-b"));
    expect(rows).toEqual([
      { name: "max_days", effectiveDate: "2026-01-14", value: 20, reference: "cl. 14(1)(b)", verification: "PRIMARY_TEXT_READ", openQuestion: "Q4" },
    ]);
  });

  it("filters by status, grade and text", async () => {
    const all = await getApi().listObligations();
    expect(filterRules(all, { verification: "UNVERIFIED" }).map((o) => o.obligation_id)).toEqual(["TAT-2019-ILLEGIBLE-ROWS"]);
    expect(filterRules(all, { q: "14(1)" }).map((o) => o.obligation_id)).toEqual(["IO-CB-2026-14-1-a", "IO-CB-2026-14-1-b"]);
  });
});

describe("rule browser page", () => {
  it("marks every draft and the unverified rule", async () => {
    await page();
    const articles = screen.getAllByRole("article");
    expect(articles.length).toBeGreaterThan(5);
    for (const a of articles) expect(within(a).getByLabelText("Warnings")).toBeDefined();
    const unverified = screen.getByRole("article", { name: /TAT-2019-ILLEGIBLE-ROWS/ });
    expect(within(unverified).getByText("Unverified: no primary text read", { exact: false })).toBeDefined();
    expect(within(unverified).getAllByText(/Unverified/).length).toBeGreaterThan(1);
  });

  it("applies the filter", async () => {
    await page({ status: "FUTURE_DATED" });
    expect(screen.getAllByRole("article").map((a) => a.id)).toEqual(["RBCCB-2026-AMEND3-FRAUD"]);
  });
});

describe("parameter display", () => {
  it("shows paise as rupees and maps as pairs", () => {
    expect(formatParam("compensation_per_day_paise", 10000)).toBe("₹100.00");
    expect(formatParam("tat_days_by_channel", { ATM: 5, IMPS: 1 })).toBe("ATM: 5 · IMPS: 1");
    expect(formatParam("follows_underlying_system", ["PPI_OFF_US"])).toBe("PPI_OFF_US");
    expect(formatParam("max_days", 20)).toBe("20");
  });
});
