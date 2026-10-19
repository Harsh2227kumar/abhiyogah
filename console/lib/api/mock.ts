import fixtures from "@/mock/fixtures.json";
import { ApiError, type EngineApi } from "./client";
import type { ComplaintDetail, ComplaintSummary, Obligation } from "./types";

/** Shape of `mock/fixtures.json`, written and validated by `mock/build_fixtures.py`. */
export interface MockFixtures {
  obligations: Obligation[];
  snapshots: {
    as_of: string;
    board: ComplaintSummary[];
    complaints: Record<string, ComplaintDetail>;
    positions: Record<string, Record<string, number>>;
  }[];
}

type Snapshot = MockFixtures["snapshots"][number];

/** The latest snapshot evaluated at or before `asOf` (default: now), or undefined. */
export function pickSnapshot(
  data: MockFixtures,
  asOf: string | undefined,
  now: () => number = Date.now,
): Snapshot | undefined {
  const at = asOf === undefined ? now() : Date.parse(asOf);
  if (Number.isNaN(at)) throw new ApiError(422, `as_of is not an ISO 8601 instant: ${asOf}`);
  let best: Snapshot | undefined;
  for (const s of data.snapshots) {
    if (Date.parse(s.as_of) <= at) best = s;
  }
  return best ?? (asOf === undefined ? data.snapshots[0] : undefined);
}

/** An `EngineApi` answered from synthetic fixtures produced by the real evaluator. */
export function createMockApi(
  data: MockFixtures = fixtures as unknown as MockFixtures,
  now: () => number = Date.now,
): EngineApi {
  const complaint = (id: string, asOf?: string): [Snapshot, ComplaintDetail] => {
    const snap = pickSnapshot(data, asOf, now);
    const detail = snap?.complaints[id];
    if (snap === undefined || detail === undefined) {
      throw new ApiError(404, `complaint ${id} is not known at ${asOf ?? "now"}`);
    }
    return [snap, detail];
  };
  return {
    kind: "mock",
    async listComplaints(asOf) {
      return pickSnapshot(data, asOf, now)?.board ?? [];
    },
    async getComplaint(id, asOf) {
      return complaint(id, asOf)[1];
    },
    async getDecision(id, obligationId, asOf) {
      const [snap, detail] = complaint(id, asOf);
      const record = detail.decisions.find((d) => d.obligation_id === obligationId);
      const position = snap.positions[id]?.[obligationId];
      if (record === undefined || position === undefined) {
        throw new ApiError(404, `no decision for ${obligationId} on ${id}`);
      }
      return { record, position, chain: detail.chain };
    },
    async listObligations() {
      return data.obligations;
    },
  };
}
