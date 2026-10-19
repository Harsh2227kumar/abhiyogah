import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import BoardPage from "@/app/page";
import type { ComplaintSummary } from "@/lib/api";
import { boardRows, filterOptions, urgencyOf } from "@/lib/board";
import { AS_OF } from "./recorded";

const row = (id: string, due: string | null, extra: Partial<ComplaintSummary> = {}): ComplaintSummary => ({
  complaint_id: id,
  channel: "UPI_P2P",
  obligation_ids: ["IO-CB-2026-14-9"],
  next_deadline: due === null ? null : { obligation_id: "IO-CB-2026-14-9", due_date: due, result: "RUNNING" },
  open_breaches: 0,
  ...extra,
});

describe("board rows", () => {
  it("sorts by days remaining with no-deadline complaints last", () => {
    const rows = boardRows([row("C", null), row("B", "2026-10-25"), row("A", "2026-10-19")], "2026-10-19");
    expect(rows.map((r) => [r.summary.complaint_id, r.daysRemaining, r.urgency])).toEqual([
      ["A", 0, "today"],
      ["B", 6, "week"],
      ["C", null, "none"],
    ]);
  });

  it("bands breached rows by the engine result even with days left", () => {
    expect(urgencyOf(row("A", "2026-11-01", { open_breaches: 1 }), 10)).toBe("breached");
    expect(urgencyOf(row("A", "2026-10-18"), -1)).toBe("breached");
    expect(urgencyOf(row("A", "2026-10-21"), 2)).toBe("soon");
    expect(urgencyOf(row("A", "2026-11-21"), 30)).toBe("later");
  });

  it("filters by obligation and channel", () => {
    const all = [row("A", null), row("B", null, { channel: "ATM", obligation_ids: ["IO-CB-2026-14-1-b"] })];
    expect(boardRows(all, "2026-10-19", { channel: "ATM" }).map((r) => r.summary.complaint_id)).toEqual(["B"]);
    expect(boardRows(all, "2026-10-19", { obligation: "IO-CB-2026-14-9" }).map((r) => r.summary.complaint_id)).toEqual(["A"]);
    expect(filterOptions(all)).toEqual({
      obligations: ["IO-CB-2026-14-1-b", "IO-CB-2026-14-9"],
      channels: ["ATM", "UPI_P2P"],
    });
  });
});

describe("board page on the recorded API", () => {
  it("puts the breached failed-transaction complaint first", async () => {
    render(await BoardPage({ searchParams: Promise.resolve({ as_of: AS_OF.now }) }));
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(6);
    const first = rows[1]!;
    expect(within(first).getByText("CMP-DEMO-0101")).toBeDefined();
    expect(within(first).getByText("TAT-2019-FAILED-TXN")).toBeDefined();
    expect(first.dataset.urgency).toBe("breached");
  });

  it("filters to the IO 20-day obligation", async () => {
    render(
      await BoardPage({ searchParams: Promise.resolve({ as_of: AS_OF.now, obligation: "IO-CB-2026-14-1-b" }) }),
    );
    const ids = screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0]!.textContent);
    expect(ids).toEqual(["CMP-DEMO-0101", "CMP-DEMO-0103", "CMP-DEMO-0105"]);
  });
});
