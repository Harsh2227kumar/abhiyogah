import type { ComplaintSummary } from "./api";
import { daysBetween } from "./format";

/** Colour band of a board row. The bands are a display choice, not a regulatory threshold. */
export type Urgency = "breached" | "today" | "soon" | "week" | "later" | "none";

export interface BoardRow {
  summary: ComplaintSummary;
  /** Days from the as-of date to the next due date; negative when overdue; null without a deadline. */
  daysRemaining: number | null;
  urgency: Urgency;
}

export interface BoardFilter {
  obligation?: string;
  channel?: string;
}

/** Band for a row, from the engine's result first and the days remaining second. */
export function urgencyOf(summary: ComplaintSummary, daysRemaining: number | null): Urgency {
  const next = summary.next_deadline;
  if (summary.open_breaches > 0 || next?.result === "BREACHED") return "breached";
  if (daysRemaining === null) return "none";
  if (daysRemaining < 0) return "breached";
  if (daysRemaining === 0) return "today";
  if (daysRemaining <= 3) return "soon";
  if (daysRemaining <= 7) return "week";
  return "later";
}

/** Filtered board rows, soonest next deadline first; complaints with no open deadline last. */
export function boardRows(
  summaries: ComplaintSummary[],
  asOfDate: string,
  filter: BoardFilter = {},
): BoardRow[] {
  return summaries
    .filter((s) => !filter.obligation || s.obligation_ids.includes(filter.obligation))
    .filter((s) => !filter.channel || s.channel === filter.channel)
    .map((summary) => {
      const due = summary.next_deadline?.due_date;
      const daysRemaining = due === undefined ? null : daysBetween(asOfDate, due);
      return { summary, daysRemaining, urgency: urgencyOf(summary, daysRemaining) };
    })
    .sort((a, b) => {
      if (a.daysRemaining === null || b.daysRemaining === null) {
        return (a.daysRemaining === null ? 1 : 0) - (b.daysRemaining === null ? 1 : 0);
      }
      return a.daysRemaining - b.daysRemaining || a.summary.complaint_id.localeCompare(b.summary.complaint_id);
    });
}

/** Distinct values offered in the board's filter menus. */
export function filterOptions(summaries: ComplaintSummary[]): { obligations: string[]; channels: string[] } {
  const obligations = new Set<string>();
  const channels = new Set<string>();
  for (const s of summaries) {
    s.obligation_ids.forEach((o) => obligations.add(o));
    if (s.channel) channels.add(s.channel);
  }
  return { obligations: [...obligations].sort(), channels: [...channels].sort() };
}
