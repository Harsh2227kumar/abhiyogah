// Display formats for India: DD-MM-YYYY dates, times in IST. Engine dates are already IST dates.

const IST = "Asia/Kolkata";

const isoDayFmt = new Intl.DateTimeFormat("en-CA", {
  timeZone: IST,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const timeFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: IST,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** The Asia/Kolkata calendar date (YYYY-MM-DD) of an instant. */
export function istDate(instant: string | number | Date): string {
  return isoDayFmt.format(new Date(instant));
}

/** `2026-10-19` -> `19-10-2026`. */
export function formatDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-");
  return `${d}-${m}-${y}`;
}

/** An instant as `19-10-2026 18:00 IST`. */
export function formatDateTime(instant: string | number | Date): string {
  return `${formatDate(istDate(instant))} ${timeFmt.format(new Date(instant))} IST`;
}

/** Whole calendar days from date `from` to date `to` (both YYYY-MM-DD); negative if `to` is earlier. */
export function daysBetween(from: string, to: string): number {
  const utc = (s: string) => {
    const [y, m, d] = s.split("-").map(Number);
    return Date.UTC(y ?? 0, (m ?? 1) - 1, d ?? 1);
  };
  return Math.round((utc(to) - utc(from)) / 86_400_000);
}

/** `WHOLLY_REJECTED` -> `Wholly rejected`; acronyms in `keep` stay upper case. */
export function humanize(code: string): string {
  const keep = new Set(["UPI", "P2P", "IMPS", "ATM", "POS", "AEPS", "APBS", "NACH", "PPI", "IO", "RBI", "RBIO", "LLM", "TAT", "MSME", "BSBD", "OD"]);
  return code
    .split("_")
    .map((w, i) => (keep.has(w) ? w : i === 0 ? w.charAt(0) + w.slice(1).toLowerCase() : w.toLowerCase()))
    .join(" ");
}
