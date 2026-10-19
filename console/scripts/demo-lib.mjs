// Shared helpers for the demo scripts. Times are IST; every date is relative to "today".

/** Today's IST date shifted by `days`, at `hhmm`, as an ISO instant with +05:30. */
export function istDay(days, hhmm = "11:00", now = Date.now()) {
  const ist = new Date(now + 330 * 60_000 + days * 86_400_000);
  return `${ist.toISOString().slice(0, 10)}T${hhmm}:00+05:30`;
}

/** The next whole minute as an IST instant (so it is after anything recorded so far), moved by `days`. */
export function istNow(days = 0, now = Date.now()) {
  const ist = new Date(Math.ceil((now + 1) / 60_000) * 60_000 + 330 * 60_000 + days * 86_400_000);
  return `${ist.toISOString().slice(0, 16)}:00+05:30`;
}

/** Read a required environment variable. */
export function env(name) {
  const v = process.env[name];
  if (!v) throw new Error(`set ${name}`);
  return v;
}
