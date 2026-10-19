import type { Provenance } from "@/lib/api";
import { provenanceLabel } from "@/lib/complaint";

/** Badge showing whether a fact came from a person, a bank system or an LLM. */
export function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  const span = provenance.span;
  const title = [
    provenanceLabel(provenance),
    span ? `span ${span.document_ref} [${span.start}–${span.end}]` : null,
    provenance.source === "LLM" ? "Extracted by an LLM: perception only, check before relying on it" : null,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <span className={`badge badge-${provenance.source.toLowerCase()}`} title={title} data-source={provenance.source}>
      {provenance.source}
    </span>
  );
}
