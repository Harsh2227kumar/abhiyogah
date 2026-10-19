import type {
  ComplaintDetail,
  ComplaintSummary,
  DecisionReplay,
  Obligation,
} from "./types";

/** The engine API as the console uses it. `asOf` is an ISO 8601 instant with an offset. */
export interface EngineApi {
  /** Which backend answers: the in-repo mock or a live engine API. */
  readonly kind: "mock" | "http";
  listComplaints(asOf?: string): Promise<ComplaintSummary[]>;
  getComplaint(complaintId: string, asOf?: string): Promise<ComplaintDetail>;
  getDecision(complaintId: string, obligationId: string, asOf?: string): Promise<DecisionReplay>;
  listObligations(): Promise<Obligation[]>;
}

/** An API call that failed; `status` follows HTTP (404 for an unknown complaint). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
