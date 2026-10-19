// Records the engine API's responses for the console's tests into test/fixtures/api.json.
// Run after seed-demo.mjs against the same API. Usage:
// ABHIYOGAH_API_URL=... ABHIYOGAH_API_KEY=<admin key> node scripts/record-fixtures.mjs
import { writeFileSync } from "node:fs";
import { env, istNow } from "./demo-lib.mjs";

const base = env("ABHIYOGAH_API_URL").replace(/\/$/, "");
const key = env("ABHIYOGAH_API_KEY");
const asOf = { now: istNow(0), later: istNow(3) };

const responses = {};
async function record(path, query = {}) {
  const url = new URL(base + path);
  for (const [k, v] of Object.entries(query)) url.searchParams.set(k, v);
  const res = await fetch(url, { headers: { accept: "application/json", "x-api-key": key } });
  if (!res.ok) throw new Error(`${url}: ${res.status} ${await res.text()}`);
  const body = await res.json();
  responses[url.pathname + url.search] = body;
  return body;
}

await record("/obligations");
for (const at of Object.values(asOf)) {
  const board = await record("/complaints", { as_of: at });
  for (const { complaint_id: id } of board) {
    const detail = await record(`/complaints/${id}`, { as_of: at });
    for (const d of detail.decisions) {
      await record(`/complaints/${id}/decisions/${encodeURIComponent(d.obligation_id)}`, { as_of: at }).catch((e) => {
        if (!String(e).includes(": 404 ")) throw e; // never stored: not triggered by any event yet
      });
    }
  }
}

const out = new URL("../test/fixtures/api.json", import.meta.url);
writeFileSync(out, JSON.stringify({ asOf, responses }, null, 1) + "\n");
console.log(`recorded ${Object.keys(responses).length} responses at ${asOf.now} and ${asOf.later}`);
