import Link from "next/link";
import { notFound } from "next/navigation";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { ResultTag } from "@/components/ResultTag";
import { VerificationTag } from "@/components/VerificationTag";
import { ApiError, getApi, type DecisionRecord, type DecisionReplay, type Obligation } from "@/lib/api";
import { parseAsOf, withAsOf } from "@/lib/asof";
import { displayFact } from "@/lib/complaint";
import { formatParam } from "@/lib/rules";
import { formatDate, formatDateTime, formatInr, humanize, localizeDates } from "@/lib/format";

type Props = {
  params: Promise<{ id: string; obligationId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

type Loaded = [DecisionReplay, Obligation | undefined, DecisionRecord | undefined];

async function load(id: string, obligationId: string, asOf: string | undefined): Promise<Loaded> {
  try {
    const api = getApi();
    const [replay, obligations, detail] = await Promise.all([
      api.getDecision(id, obligationId, asOf),
      api.listObligations(),
      api.getComplaint(id, asOf),
    ]);
    return [
      replay,
      obligations.find((o) => o.obligation_id === obligationId),
      detail.decisions.find((d) => d.obligation_id === obligationId),
    ];
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
}

const json = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));

/** The latest stored decision record rendered as a clause-cited trace, with its hash and chain status. */
export default async function DecisionPage({ params, searchParams }: Props) {
  const { id, obligationId } = await params;
  const asOf = parseAsOf((await searchParams).as_of);
  const [{ record: r, position, chain }, ob, live] = await load(decodeURIComponent(id), decodeURIComponent(obligationId), asOf);
  const dl = r.deadline;
  const brokenHere = !chain.verified && chain.broken_at !== null && chain.broken_at !== undefined && chain.broken_at <= position;

  return (
    <article>
      <p>
        <Link href={withAsOf(`/complaints/${encodeURIComponent(r.complaint_id)}`, asOf)}>← Complaint {r.complaint_id}</Link>
      </p>
      <h1>
        {r.obligation_id} <ResultTag result={r.result} />
      </h1>
      {live && live.result !== r.result && (
        <p className="notice" role="note">
          Evaluated live at {formatDateTime(live.as_of)} this obligation is <ResultTag result={live.result} />. The record
          below is the latest one in the ledger, from {formatDateTime(r.as_of)}; a new record is written when an event
          arrives or the scheduler re-evaluates.
        </p>
      )}

      <section aria-labelledby="source">
        <h2 id="source">Obligation</h2>
        <dl className="kv">
          <dt>Clause</dt>
          <dd>
            {ob ? (
              <>
                {ob.instrument}, cl. {r.clause}
                {ob.instrument_ref && <span className="muted"> ({ob.instrument_ref})</span>} ·{" "}
                <a href={ob.source_url} rel="noreferrer noopener" target="_blank">
                  source text
                </a>
              </>
            ) : (
              <>cl. {r.clause}</>
            )}
          </dd>
          {ob && (
            <>
              <dt>Status</dt>
              <dd>
                <span className={`status status-${ob.status.toLowerCase()}`}>{humanize(ob.status)}</span>{" "}
                <VerificationTag grade={ob.verification} />
              </dd>
            </>
          )}
          <dt>Version</dt>
          <dd>
            <code>{r.obligation_version}</code>
          </dd>
          <dt>Anchor date</dt>
          <dd>{r.anchor_date ? formatDate(r.anchor_date) : "—"}</dd>
          <dt>Evaluated at</dt>
          <dd>{formatDateTime(r.as_of)}</dd>
          <dt>Calendar version</dt>
          <dd>
            <code>{r.calendar_version ?? "—"}</code>
          </dd>
        </dl>
      </section>

      <section aria-labelledby="inputs">
        <h2 id="inputs">Inputs</h2>
        <table>
          <thead>
            <tr>
              <th scope="col">Fact</th>
              <th scope="col">Value</th>
              <th scope="col">Source</th>
              <th scope="col">Event</th>
            </tr>
          </thead>
          <tbody>
            {(r.input_facts ?? []).map((f) => (
              <tr key={f.name}>
                <td>
                  <code>{f.name}</code>
                </td>
                <td>{f.value !== null && typeof f.value === "object" ? json(f.value) : displayFact(f.name, f.value)}</td>
                <td>
                  <ProvenanceBadge provenance={f.provenance} />
                </td>
                <td>
                  <code>{f.event_id ?? "—"}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="parameters">
        <h2 id="parameters">Parameters</h2>
        {(r.parameters ?? []).length === 0 ? (
          <p>None used.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th scope="col">Parameter</th>
                <th scope="col">Value</th>
                <th scope="col">In force from</th>
                <th scope="col">Reference</th>
                <th scope="col">Verification</th>
              </tr>
            </thead>
            <tbody>
              {(r.parameters ?? []).map((p) => (
                <tr key={p.name}>
                  <td>
                    <code>{p.name}</code>
                  </td>
                  <td>{formatParam(p.name, p.value)}</td>
                  <td>{formatDate(p.effective_date)}</td>
                  <td>{localizeDates(p.reference)}</td>
                  <td>
                    <VerificationTag grade={p.verification} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="trace">
        <h2 id="trace">Trace</h2>
        <ol className="trace">
          {(r.condition_trace ?? []).map((t, i) => (
            <li key={i} className={t.result ? "pass" : "fail"}>
              <span aria-label={t.result ? "true" : "false"}>{t.result ? "✓" : "✗"}</span> <code>{t.condition}</code>
              {t.detail && <span className="muted"> — {localizeDates(t.detail)}</span>}
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="outcome">
        <h2 id="outcome">Deadline and outcome</h2>
        <dl className="kv">
          <dt>Deadline</dt>
          <dd>
            {dl ? (
              <>
                {formatDate(dl.due_date)} — {dl.rule ? localizeDates(dl.rule) : "—"}
                {dl.start_date && <> from {formatDate(dl.start_date)}</>} ({humanize(dl.start_event)}
                {dl.stop_event && <> → {humanize(dl.stop_event)}</>}; {humanize(dl.basis).toLowerCase()} days,{" "}
                {humanize(dl.basis_status).toLowerCase()})
              </>
            ) : (
              "No deadline"
            )}
          </dd>
          <dt>Result</dt>
          <dd>
            <ResultTag result={r.result} />
          </dd>
          <dt>Breach</dt>
          <dd>
            {r.breach
              ? `${r.breach.days_late} day${r.breach.days_late === 1 ? "" : "s"} late (due ${formatDate(r.breach.due_date)}${
                  r.breach.stop_date ? `, stopped ${formatDate(r.breach.stop_date)}` : ""
                })`
              : "None"}
          </dd>
          <dt>Compensation</dt>
          <dd>
            {r.compensation ? (
              <>
                {formatInr(r.compensation.amount_paise)} — <code>{r.compensation.formula}</code>
                {r.compensation.inputs && Object.keys(r.compensation.inputs).length > 0 && (
                  <span className="muted"> ({Object.entries(r.compensation.inputs).map(([k, v]) => `${k} = ${v !== null && typeof v === "object" ? json(v) : displayFact(k, v)}`).join(", ")})</span>
                )}
              </>
            ) : (
              "None"
            )}
          </dd>
          <dt>Required actions</dt>
          <dd>
            {(r.required_actions ?? []).length === 0
              ? "None"
              : (r.required_actions ?? [])
                  .map((a) => `${humanize(a.action)}${a.due_date ? ` by ${formatDate(a.due_date)}` : ""}${a.reason ? ` (${localizeDates(a.reason)})` : ""}`)
                  .join("; ")}
          </dd>
        </dl>
      </section>

      <section aria-labelledby="ledger">
        <h2 id="ledger">Ledger</h2>
        <dl className="kv">
          <dt>Record</dt>
          <dd>
            {position + 1} of {chain.length}
          </dd>
          <dt>Hash</dt>
          <dd>
            <code className="hash">{r.hash ?? "unsealed"}</code>
          </dd>
          <dt>Previous hash</dt>
          <dd>
            <code className="hash">{r.prev_hash}</code>
          </dd>
          <dt>Chain</dt>
          <dd className={chain.verified ? "chain-ok" : "chain-broken"}>
            {chain.verified
              ? "Verified: every record links to its predecessor and matches its hash."
              : `Broken at record ${(chain.broken_at ?? 0) + 1}${brokenHere ? "; this record is at or after the break and cannot be trusted" : ""}.`}
          </dd>
        </dl>
      </section>
    </article>
  );
}
