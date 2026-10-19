import type { ComplaintFacts, DecisionRecord, Provenance } from "./api";
import { formatDate, formatInr, humanize } from "./format";

export interface FactRow {
  name: string;
  display: string;
  provenance: Provenance;
  eventId: string;
  recordedAt: string;
}

type AnyFact = { value: unknown; provenance: Provenance; event_id: string; recorded_at: string };

const isDateFact = (name: string) => /(_date(_t|_r)?|_as_on)$/.test(name);

/** How one fact value is shown: dates DD-MM-YYYY, paise as ₹, enum codes humanized. */
export function displayFact(name: string, value: unknown): string {
  if (typeof value === "string" && isDateFact(name)) return formatDate(value);
  if (name.endsWith("_paise") && typeof value === "number") return formatInr(value);
  if (typeof value === "string" && /^[A-Z0-9_]+$/.test(value)) return humanize(value);
  return String(value);
}

/** Every known fact, in the order the engine's data dictionary lists them. */
export function factRows(facts: ComplaintFacts): FactRow[] {
  const rows: FactRow[] = [];
  for (const [name, raw] of Object.entries(facts)) {
    if (name === "complaint_id" || raw === null || raw === undefined) continue;
    const fact = raw as AnyFact;
    rows.push({
      name,
      display: displayFact(name, fact.value),
      provenance: fact.provenance,
      eventId: fact.event_id,
      recordedAt: fact.recorded_at,
    });
  }
  return rows;
}

/** Decisions that ran a clock, soonest due first. */
export function clocks(decisions: DecisionRecord[]): DecisionRecord[] {
  return decisions
    .filter((d) => d.deadline)
    .sort((a, b) => (a.deadline!.due_date < b.deadline!.due_date ? -1 : a.deadline!.due_date > b.deadline!.due_date ? 1 : 0));
}

/** A one-line description of who asserted something. */
export function provenanceLabel(p: Provenance): string {
  if (p.source === "LLM") return `LLM ${p.model ?? "?"} · prompt ${p.prompt_version ?? "?"}`;
  return `${humanize(p.source)} · ${p.actor ?? "?"}`;
}
