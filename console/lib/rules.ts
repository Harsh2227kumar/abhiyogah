import type { Obligation, Verification } from "./api";
import { formatDate, formatInr } from "./format";

export interface ParameterRow {
  name: string;
  effectiveDate: string;
  value: unknown;
  reference: string;
  verification: Verification;
  openQuestion: string | null;
}

/** Every dated value of every parameter, newest first within a parameter. */
export function parameterRows(ob: Obligation): ParameterRow[] {
  const rows: ParameterRow[] = [];
  for (const [name, history] of Object.entries(ob.parameters ?? {})) {
    const dated = Object.entries(history).sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0));
    for (const [effectiveDate, v] of dated) {
      rows.push({
        name,
        effectiveDate,
        value: v.value,
        reference: v.reference,
        verification: v.verification,
        openQuestion: v.open_question ?? null,
      });
    }
  }
  return rows;
}

/** Why an obligation needs care before anyone relies on it; empty when it is signed off and primary-read. */
export function warnings(ob: Obligation): string[] {
  const out: string[] = [];
  if (ob.status === "DRAFT") out.push("Draft: not signed off by the owner");
  if (ob.status === "FUTURE_DATED") out.push(`Not yet in force (valid from ${formatDate(ob.valid_from)})`);
  if (ob.verification === "UNVERIFIED") out.push("Unverified: no primary text read");
  if (ob.verification === "CONFLICTING") out.push("Sources conflict");
  if (ob.verification === "SECONDARY_ONLY") out.push("Secondary sources only");
  const weakParams = parameterRows(ob).filter((p) => p.verification !== "PRIMARY_TEXT_READ");
  if (weakParams.length > 0 && ob.verification === "PRIMARY_TEXT_READ") {
    out.push(`Parameter not primary-read: ${[...new Set(weakParams.map((p) => p.name))].join(", ")}`);
  }
  const questions = [...new Set(parameterRows(ob).flatMap((p) => (p.openQuestion ? [p.openQuestion] : [])))];
  if (questions.length > 0) out.push(`Open question ${questions.join(", ")}`);
  return out;
}

export interface RuleFilter {
  status?: string;
  verification?: string;
  q?: string;
}

/** Obligations matching the filter, sorted by ID. */
export function filterRules(obligations: Obligation[], f: RuleFilter): Obligation[] {
  const q = f.q?.trim().toLowerCase();
  return obligations
    .filter((o) => !f.status || o.status === f.status)
    .filter((o) => !f.verification || o.verification === f.verification)
    .filter(
      (o) => !q || [o.obligation_id, o.instrument, o.clause, o.instrument_ref ?? ""].some((s) => s.toLowerCase().includes(q)),
    )
    .sort((a, b) => a.obligation_id.localeCompare(b.obligation_id));
}

/** A parameter value for display: paise as ₹, maps as `KEY: v` pairs, lists comma-separated. */
export function formatParam(name: string, value: unknown): string {
  if (name.endsWith("_paise") && typeof value === "number") return formatInr(value);
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (value !== null && typeof value === "object") {
    return Object.entries(value)
      .map(([k, v]) => `${k}: ${String(v)}`)
      .join(" · ");
  }
  return String(value);
}
