import { VerificationTag } from "@/components/VerificationTag";
import { getApi } from "@/lib/api";
import { formatDate, humanize } from "@/lib/format";
import { filterRules, formatParam, parameterRows, warnings } from "@/lib/rules";

type Search = Promise<Record<string, string | string[] | undefined>>;

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || undefined;
const STATUSES = ["DRAFT", "FUTURE_DATED", "IN_FORCE", "SUPERSEDED", "REPEALED_BUT_SAVED"];
const GRADES = ["PRIMARY_TEXT_READ", "SECONDARY_ONLY", "UNVERIFIED", "CONFLICTING"];

/** Rule browser: every obligation with its clause, source, grade and status. */
export default async function RulesPage({ searchParams }: { searchParams: Search }) {
  const params = await searchParams;
  const filter = { status: one(params.status), verification: one(params.verification), q: one(params.q) };
  const all = await getApi().listObligations();
  const rules = filterRules(all, filter);

  return (
    <section>
      <h1>Rule browser</h1>
      <p className="muted">
        {all.length} obligations in the loaded rule pack. Only the owner can set a rule in force; drafts and
        anything not read in the primary text are marked.
      </p>
      <form className="filters" method="get" aria-label="Filter rules">
        <label>
          Search <input name="q" defaultValue={filter.q ?? ""} placeholder="ID, instrument or clause" />
        </label>
        <label>
          Status{" "}
          <select name="status" defaultValue={filter.status ?? ""}>
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Verification{" "}
          <select name="verification" defaultValue={filter.verification ?? ""}>
            <option value="">All</option>
            {GRADES.map((g) => (
              <option key={g} value={g}>
                {humanize(g)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">Apply</button>
      </form>

      {rules.map((ob) => {
        const warn = warnings(ob);
        return (
          <article
            key={ob.obligation_id}
            id={ob.obligation_id}
            className={`rule ${warn.length > 0 ? "rule-flagged" : ""}`}
            data-status={ob.status}
            data-verification={ob.verification}
            aria-labelledby={`h-${ob.obligation_id}`}
          >
            <h2 id={`h-${ob.obligation_id}`}>
              {ob.obligation_id} <span className={`status status-${ob.status.toLowerCase()}`}>{humanize(ob.status)}</span>{" "}
              <VerificationTag grade={ob.verification} />
            </h2>
            {warn.length > 0 && (
              <ul className="warnings" aria-label="Warnings">
                {warn.map((w) => (
                  <li key={w}>⚠ {w}</li>
                ))}
              </ul>
            )}
            <dl className="kv">
              <dt>Instrument</dt>
              <dd>
                {ob.instrument}
                {ob.instrument_ref && <span className="muted"> ({ob.instrument_ref})</span>}
              </dd>
              <dt>Clause</dt>
              <dd>
                {ob.clause} ·{" "}
                <a href={ob.source_url} rel="noreferrer noopener" target="_blank">
                  source text
                </a>
              </dd>
              <dt>Type</dt>
              <dd>
                {humanize(ob.deontic)} of the {ob.subject}
              </dd>
              <dt>Trigger</dt>
              <dd>
                {humanize(ob.trigger.event)}
                {ob.trigger.condition && (
                  <>
                    {" "}
                    when <code>{ob.trigger.condition}</code>
                  </>
                )}
              </dd>
              {ob.clock && (
                <>
                  <dt>Clock</dt>
                  <dd>
                    {humanize(ob.clock.start)} → {(ob.clock.stop ?? []).map(humanize).join(" or ") || "—"} (
                    {humanize(ob.clock.basis).toLowerCase()} days, {humanize(ob.clock.basis_status).toLowerCase()})
                  </dd>
                </>
              )}
              <dt>Valid</dt>
              <dd>
                {formatDate(ob.valid_from)} – {ob.valid_to ? formatDate(ob.valid_to) : "open"}
              </dd>
              {ob.signed_off_by && (
                <>
                  <dt>Signed off by</dt>
                  <dd>{ob.signed_off_by}</dd>
                </>
              )}
            </dl>
            {parameterRows(ob).length > 0 && (
              <table className="params">
                <thead>
                  <tr>
                    <th scope="col">Parameter</th>
                    <th scope="col">From</th>
                    <th scope="col">Value</th>
                    <th scope="col">Reference</th>
                    <th scope="col">Verification</th>
                    <th scope="col">Open question</th>
                  </tr>
                </thead>
                <tbody>
                  {parameterRows(ob).map((p) => (
                    <tr key={`${p.name}-${p.effectiveDate}`}>
                      <td>
                        <code>{p.name}</code>
                      </td>
                      <td className="nowrap">{formatDate(p.effectiveDate)}</td>
                      <td>
                        {formatParam(p.name, p.value)}
                      </td>
                      <td>{p.reference}</td>
                      <td>
                        <VerificationTag grade={p.verification} />
                      </td>
                      <td>{p.openQuestion ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </article>
        );
      })}
      {rules.length === 0 && <p>No obligations match.</p>}
    </section>
  );
}
