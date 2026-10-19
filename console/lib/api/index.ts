// The one place the console chooses its backend. Pages import `getApi` and the types from here.
import type { EngineApi } from "./client";
import { createHttpApi } from "./http";
import { createMockApi } from "./mock";

export { ApiError, type EngineApi } from "./client";
export type * from "./types";

let api: EngineApi | undefined;

/** The live engine API when `ABHIYOGAH_API_URL` is set, else the synthetic mock. */
export function getApi(): EngineApi {
  api ??= process.env.ABHIYOGAH_API_URL
    ? createHttpApi(process.env.ABHIYOGAH_API_URL)
    : createMockApi();
  return api;
}
