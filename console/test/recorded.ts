// Replays engine API responses recorded by scripts/record-fixtures.mjs from a live API seeded with
// synthetic complaints (scripts/seed-demo.mjs), so page tests run the real HTTP client offline.
import recording from "./fixtures/api.json";

export const API_URL = "http://engine.recorded";
export const AS_OF = recording.asOf;

const responses = recording.responses as Record<string, unknown>;

/** A `fetch` that answers from the recording; anything not recorded is a 404, like the API. */
export const replayFetch = (async (input: URL | RequestInfo) => {
  const url = new URL(input instanceof Request ? input.url : String(input));
  const body = responses[url.pathname + url.search];
  return body === undefined
    ? new Response(JSON.stringify({ detail: `not recorded: ${url.pathname}${url.search}` }), { status: 404 })
    : new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
}) as typeof fetch;

/** A recorded response, for tests that need to start from real data. */
export function recorded<T>(path: string, asOf?: string): T {
  const key = asOf ? `${path}?as_of=${encodeURIComponent(asOf)}` : path;
  const body = responses[key];
  if (body === undefined) throw new Error(`not recorded: ${key}`);
  return structuredClone(body) as T;
}
