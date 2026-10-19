import Link from "next/link";
import { notFound } from "next/navigation";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { ResultTag } from "@/components/ResultTag";
import { ApiError, getApi, type ComplaintDetail } from "@/lib/api";
import { parseAsOf, withAsOf } from "@/lib/asof";
import { clocks, displayFact, factRows } from "@/lib/complaint";
import { formatDate, formatDateTime, formatInr, humanize, localizeDates } from "@/lib/format";

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

async function load(id: string, asOf: string | undefined): Promise<ComplaintDetail> {
  try {
    return await getApi().getComplaint(id, asOf);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
}

/** One complaint: events, facts with provenance, clocks, breaches and required actions. */
export default async function ComplaintPage({ params, searchParams }: Props) {
  const { id } = await params;
  const asOf = parseAsOf((await searchParams).as_of);
  const c = await load(decodeURIComponent(id), asOf);
  const replay = (obligationId: string) =>
    withAsOf(`/complaints/${encodeURIComponent(c.complaint_id)}/decisions/${encodeURIComponent(obligationId)}`, asOf);
  const breaches = c.decisions.filter((d) => d.breach);
  const actions = c.decisions.flatMap((d) => (d.required_actions ?? []).map((a) => ({ ...a, obligation_id: d.obligation_id })));

  return (
    <article>
      <p>
        <Link href={withAsOf("/", asOf)}>← Deadline board</Link>
      </p>
      <h1>Complaint {c.complaint_id}</h1>
      <p className="muted">
        Evaluated at {formatDateTime(c.as_of)} ·{" "}
        <span className={c.chain.verified ? "chain-ok" : "chain-broken"}>
          {c.chain.verified
            ? `Decision chain verified (${c.chain.length} records)`
            : `Decision chain broken at record ${c.chain.broken_at ?? "?"} of ${c.chain.length}`}
        </span>
      </p>

      <section aria-labelledby="breaches">
        <h2 id="breaches">Breaches</h2>
        {breaches.length === 0 ? (
          <p>None.</p>
        ) : (
          <ul>
            {breaches.map((d) => (
              <li key={d.obligation_id} className="breach">
                <Link href={replay(d.obligation_id)}>{d.obligation_id}</Link> (cl. {d.clause}): due{" "}
                {formatDate(d.breach!.due_date)}
                {d.breach!.stop_date ? `, stopped ${formatDate(d.breach!.stop_date)}` : ", not stopped"} —{" "}
                {d.breach!.days_late} day{d.breach!.days_late === 1 ? "" : "s"} late
                {d.compensation && <> · compensation {formatInr(d.compensation.amount_paise)}</>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="actions">
        <h2 id="actions">Required actions</h2>
        {actions.length === 0 ? (
          <p>None.</p>
        ) : (
          <ul>
            {actions.map((a) => (
              <li key={`${a.obligation_id}-${a.action}`}>
                <strong>{humanize(a.action)}</strong>
                {a.due_date && <> by {formatDate(a.due_date)}</>} ({a.obligation_id}){a.reason && <> — {localizeDates(a.reason)}</>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="clocks">
        <h2 id="clocks">Clocks</h2>
        <table>
          <thead>
            <tr>
              <th scope="col">Obligation</th>
              <th scope="col">Clause</th>
              <th scope="col">Start</th>
              <th scope="col">Stop</th>
              <th scope="col">Rule</th>
              <th scope="col">Due</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            {clocks(c.decisions).map((d) => {
              const dl = d.deadline!;
              return (
                <tr key={d.obligation_id}>
                  <td>
                    <Link href={replay(d.obligation_id)}>{d.obligation_id}</Link>
                  </td>
                  <td>{d.clause}</td>
                  <td>
                    {humanize(dl.start_event)}
                    {dl.start_date && <> · {formatDate(dl.start_date)}</>}
                  </td>
                  <td>{dl.stop_event ? humanize(dl.stop_event) : "—"}</td>
                  <td>
                    {dl.rule ? localizeDates(dl.rule) : "—"}{" "}
                    <span className="muted">
                      ({humanize(dl.basis)}, {humanize(dl.basis_status).toLowerCase()})
                    </span>
                  </td>
                  <td>{formatDate(dl.due_date)}</td>
                  <td>
                    <ResultTag result={d.result} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <details>
          <summary>Obligations without a running clock</summary>
          <ul>
            {c.decisions
              .filter((d) => !d.deadline)
              .map((d) => (
                <li key={d.obligation_id}>
                  <Link href={replay(d.obligation_id)}>{d.obligation_id}</Link>: <ResultTag result={d.result} />
                </li>
              ))}
          </ul>
        </details>
      </section>

      <section aria-labelledby="facts">
        <h2 id="facts">Facts</h2>
        <table>
          <thead>
            <tr>
              <th scope="col">Fact</th>
              <th scope="col">Value</th>
              <th scope="col">Source</th>
              <th scope="col">Event</th>
              <th scope="col">Recorded</th>
            </tr>
          </thead>
          <tbody>
            {factRows(c.facts).map((f) => (
              <tr key={f.name}>
                <td>
                  <code>{f.name}</code>
                </td>
                <td>{f.display}</td>
                <td>
                  <ProvenanceBadge provenance={f.provenance} />
                </td>
                <td>
                  <code>{f.eventId}</code>
                </td>
                <td>{formatDateTime(f.recordedAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="timeline">
        <h2 id="timeline">Event timeline</h2>
        <ol className="timeline">
          {[...c.events]
            .sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at))
            .map((e) => (
              <li key={e.event_id} id={e.event_id}>
                <time dateTime={e.occurred_at}>{formatDateTime(e.occurred_at)}</time>{" "}
                <strong>{humanize(e.type)}</strong> <ProvenanceBadge provenance={e.provenance} />{" "}
                <code className="muted">{e.event_id}</code>
                {Object.keys(e.payload ?? {}).length > 0 && (
                  <div className="payload">
                    {Object.entries(e.payload ?? {})
                      .map(([k, v]) => `${k}: ${v === null || typeof v !== "object" ? displayFact(k, v) : JSON.stringify(v)}`)
                      .join(" · ")}
                  </div>
                )}
                <div className="muted small">recorded {formatDateTime(e.recorded_at)}</div>
              </li>
            ))}
        </ol>
      </section>
    </article>
  );
}
