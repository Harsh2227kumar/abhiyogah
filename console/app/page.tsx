import Link from "next/link";
import { getApi } from "@/lib/api";
import { asOfDate, parseAsOf, withAsOf } from "@/lib/asof";
import { boardRows, filterOptions, type BoardRow } from "@/lib/board";
import { formatDate, humanize } from "@/lib/format";

type Search = Promise<Record<string, string | string[] | undefined>>;

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || undefined;

function daysLabel(row: BoardRow): string {
  const d = row.daysRemaining;
  if (d === null) return "—";
  if (d === 0) return "Due today";
  return d > 0 ? `${d} day${d === 1 ? "" : "s"} left` : `${-d} day${d === -1 ? "" : "s"} overdue`;
}

/** Deadline board: complaints by next deadline, coloured by days remaining. */
export default async function BoardPage({ searchParams }: { searchParams: Search }) {
  const params = await searchParams;
  const asOf = parseAsOf(params.as_of);
  const filter = { obligation: one(params.obligation), channel: one(params.channel) };
  const summaries = await getApi().listComplaints(asOf);
  const options = filterOptions(summaries);
  const rows = boardRows(summaries, asOfDate(asOf), filter);

  return (
    <section>
      <h1>Deadline board</h1>
      <form className="filters" method="get" aria-label="Filter complaints">
        {asOf && <input type="hidden" name="as_of" value={asOf} />}
        <label>
          Obligation{" "}
          <select name="obligation" defaultValue={filter.obligation ?? ""}>
            <option value="">All</option>
            {options.obligations.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
        <label>
          Channel{" "}
          <select name="channel" defaultValue={filter.channel ?? ""}>
            <option value="">All</option>
            {options.channels.map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">Apply</button>
      </form>

      <table className="board">
        <thead>
          <tr>
            <th scope="col">Complaint</th>
            <th scope="col">Channel</th>
            <th scope="col">Next deadline</th>
            <th scope="col">Obligation</th>
            <th scope="col">Due</th>
            <th scope="col">Engine result</th>
            <th scope="col">Breaches</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const s = row.summary;
            const next = s.next_deadline;
            return (
              <tr key={s.complaint_id} className={`urgency-${row.urgency}`} data-urgency={row.urgency}>
                <td>
                  <Link href={withAsOf(`/complaints/${encodeURIComponent(s.complaint_id)}`, asOf)}>
                    {s.complaint_id}
                  </Link>
                </td>
                <td>{s.channel ? humanize(s.channel) : "—"}</td>
                <td>
                  <span className="pill">{daysLabel(row)}</span>
                </td>
                <td>{next?.obligation_id ?? "—"}</td>
                <td>{next ? formatDate(next.due_date) : "—"}</td>
                <td>{next ? humanize(next.result) : "No open deadline"}</td>
                <td>{s.open_breaches}</td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7}>No complaints match.</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="legend">
        Colours show days to the next open deadline (overdue, today, ≤3 days, ≤7 days, later). The
        result and any breach come from the engine.
      </p>
    </section>
  );
}
