import type { DecisionResult } from "@/lib/api";
import { humanize } from "@/lib/format";

/** The engine's result for one obligation, coloured by outcome. */
export function ResultTag({ result }: { result: DecisionResult }) {
  return <span className={`result result-${result.toLowerCase()}`}>{humanize(result)}</span>;
}
