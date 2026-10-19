// Names for the generated API schemas. Never declare API shapes by hand: regenerate with `pnpm openapi`.
import type { components } from "./generated/schema";

type Schemas = components["schemas"];

export type ComplaintSummary = Schemas["ComplaintSummary"];
export type ComplaintDetail = Schemas["ComplaintDetail"];
export type ComplaintEvent = Schemas["ComplaintEvent"];
export type ComplaintFacts = Schemas["ComplaintFacts"];
export type DecisionRecord = Schemas["DecisionRecord"];
export type DecisionReplay = Schemas["DecisionReplay"];
export type DecisionResult = Schemas["DecisionResult"];
export type ChainStatus = Schemas["ChainStatus"];
export type Deadline = Schemas["Deadline"];
export type Breach = Schemas["Breach"];
export type Provenance = Schemas["Provenance"];
export type FactSource = Schemas["FactSource"];
export type Channel = Schemas["Channel"];
export type Obligation = Schemas["Obligation"];
export type RuleStatus = Schemas["RuleStatus"];
export type Verification = Schemas["Verification"];
