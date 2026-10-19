// The `as_of` instant a page is viewed at, carried in the `?as_of=` query parameter.
import { istDate } from "./format";

/** A valid ISO 8601 instant with an explicit offset, or undefined for "now". */
export function parseAsOf(raw: string | string[] | undefined): string | undefined {
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (!v) return undefined;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/.test(v)) return undefined;
  return Number.isNaN(Date.parse(v)) ? undefined : v;
}

/** A path with the `as_of` parameter kept, so links stay at the same moment. */
export function withAsOf(path: string, asOf: string | undefined): string {
  if (!asOf) return path;
  return `${path}${path.includes("?") ? "&" : "?"}as_of=${encodeURIComponent(asOf)}`;
}

/** The IST date a page is viewed at: the `as_of` date, else today in IST. */
export function asOfDate(asOf: string | undefined): string {
  return istDate(asOf ?? Date.now());
}

/** An instant as the value of a `datetime-local` input, in IST (`YYYY-MM-DDTHH:mm`). */
export function toIstInput(instant: string | number): string {
  const ist = new Date(new Date(instant).getTime() + 330 * 60_000);
  return ist.toISOString().slice(0, 16);
}

/** A `datetime-local` value read as IST, as an instant with a +05:30 offset; undefined if invalid. */
export function fromIstInput(value: string): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return undefined;
  return parseAsOf(`${value}:00+05:30`);
}

/** `asOf` (or now) moved by `days` whole days, as a +05:30 instant. */
export function shiftDays(asOf: string | undefined, days: number, now: () => number = Date.now): string {
  const base = asOf === undefined ? now() : Date.parse(asOf);
  return `${toIstInput(base + days * 86_400_000)}:00+05:30`;
}
