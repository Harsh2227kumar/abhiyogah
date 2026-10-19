"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { fromIstInput, parseAsOf, shiftDays, toIstInput } from "@/lib/asof";
import { formatDateTime } from "@/lib/format";

/** Admin control that sets `as_of` for every page, for demos and replay. Times are IST. */
export function TimeTravel() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const asOf = parseAsOf(search.get("as_of") ?? undefined);
  const [value, setValue] = useState(() => (asOf ? toIstInput(asOf) : ""));
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState(asOf);
  if (shown !== asOf) {
    // as_of changed by navigation (a link or the back button): show the new moment.
    setShown(asOf);
    setValue(asOf ? toIstInput(asOf) : "");
  }

  const go = (next: string | undefined) => {
    const params = new URLSearchParams(search.toString());
    if (next) params.set("as_of", next);
    else params.delete("as_of");
    setValue(next ? toIstInput(next) : "");
    setError(null);
    const qs = params.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  };

  return (
    <form
      className={`timetravel ${asOf ? "timetravel-active" : ""}`}
      aria-label="Time travel"
      onSubmit={(e) => {
        e.preventDefault();
        const next = fromIstInput(value);
        if (next) go(next);
        else setError("Enter a date and time");
      }}
    >
      <span className="admin-tag">Admin</span>
      <label>
        As of (IST){" "}
        <input type="datetime-local" value={value} onChange={(e) => setValue(e.target.value)} aria-invalid={error !== null} />
      </label>
      <button type="submit">Go</button>
      <button type="button" onClick={() => go(shiftDays(asOf, 1))}>
        +1 day
      </button>
      <button type="button" onClick={() => go(undefined)} disabled={!asOf}>
        Now
      </button>
      <span role="status" className={asOf ? "timetravel-note" : "muted"}>
        {error ?? (asOf ? `Time travel: viewing as of ${formatDateTime(asOf)}` : "Live")}
      </span>
    </form>
  );
}
