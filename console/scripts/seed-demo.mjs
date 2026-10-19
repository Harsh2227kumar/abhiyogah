// Posts five synthetic complaints to a running engine API, dated relative to today (IST), so the
// plan's demo can be clicked through: CMP-DEMO-0101's 20-day IO clock is due in two days and breaches
// after time travel. Usage: ABHIYOGAH_API_URL=... ABHIYOGAH_WRITER_KEY=... node scripts/seed-demo.mjs
import { env, istDay } from "./demo-lib.mjs";

const crm = { source: "SYSTEM" };
const officer = { source: "HUMAN" };
const extractor = {
  source: "LLM",
  model: "synthetic-extractor",
  prompt_version: "triage-extract-v0",
  span: { document_ref: "DOC-SYN-0101", start: 42, end: 97 },
};

/** [type, day offset, HH:MM, payload, provenance] per event. */
const COMPLAINTS = {
  // Wholly rejected, never referred to the IO: the 20-day clock is due in two days.
  "CMP-DEMO-0101": [
    ["BANK_RECEIVED", -18, "10:30", {}, crm],
    ["ACKNOWLEDGED", -18, "10:35", {}, crm],
    ["FACTS_RECORDED", -18, "10:40", { issue_type: "FAILED_TRANSACTION", channel: "UPI_P2P", amount_paise: 245000, transaction_date_t: istDay(-20).slice(0, 10) }, extractor],
    ["OUTCOME_SET", -11, "16:00", { outcome: "WHOLLY_REJECTED" }, officer],
  ],
  // Fully resolved, final reply inside 30 days.
  "CMP-DEMO-0102": [
    ["BANK_RECEIVED", -40, "09:15", { channel: "ATM" }, crm],
    ["ACKNOWLEDGED", -40, "09:20", {}, crm],
    ["OUTCOME_SET", -27, "15:00", { outcome: "FULLY_RESOLVED" }, officer],
    ["FINAL_REPLY_SENT", -26, "12:00", {}, officer],
  ],
  // Partially resolved; referred to the IO late and replied to late.
  "CMP-DEMO-0103": [
    ["BANK_RECEIVED", -50, "14:00", { channel: "IMPS" }, crm],
    ["ACKNOWLEDGED", -49, "10:00", {}, crm],
    ["OUTCOME_SET", -42, "17:00", { outcome: "PARTIALLY_RESOLVED" }, officer],
    ["IO_REFERRED", -27, "11:00", {}, officer],
    ["IO_DECIDED", -13, "16:30", {}, officer],
    ["FINAL_REPLY_SENT", -9, "12:00", {}, officer],
  ],
  // Received a week ago; the 30-day reply clock is running.
  "CMP-DEMO-0104": [
    ["BANK_RECEIVED", -7, "10:00", { channel: "POS_CARD_PRESENT" }, crm],
    ["ACKNOWLEDGED", -7, "10:05", {}, crm],
  ],
  // Wholly rejected, referred and replied to on time.
  "CMP-DEMO-0105": [
    ["BANK_RECEIVED", -35, "12:00", { channel: "UPI_MERCHANT" }, crm],
    ["ACKNOWLEDGED", -35, "12:05", {}, crm],
    ["OUTCOME_SET", -28, "15:00", { outcome: "WHOLLY_REJECTED" }, officer],
    ["IO_REFERRED", -20, "10:00", {}, officer],
    ["IO_DECIDED", -10, "16:00", {}, officer],
    ["FINAL_REPLY_SENT", -7, "11:00", {}, officer],
  ],
};

const base = env("ABHIYOGAH_API_URL").replace(/\/$/, "");
const key = env("ABHIYOGAH_WRITER_KEY");

for (const [complaintId, rows] of Object.entries(COMPLAINTS)) {
  // One event per request, in order, so each lands in the ledger as its own evaluation.
  for (const [i, [type, days, hhmm, payload, prov]] of rows.entries()) {
    const event = { event_id: `${complaintId}-${String(i + 1).padStart(2, "0")}`, type, occurred_at: istDay(days, hhmm), payload, ...prov };
    const res = await fetch(`${base}/complaints/${complaintId}/events`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": key },
      body: JSON.stringify({ events: [event] }),
    });
    if (!res.ok) throw new Error(`${complaintId} ${type}: ${res.status} ${await res.text()}`);
    const out = await res.json();
    if (out.evaluation_error) throw new Error(`${complaintId} ${type}: ${out.evaluation_error}`);
  }
  console.log(`seeded ${complaintId} (${rows.length} events)`);
}
